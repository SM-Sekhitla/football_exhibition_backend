import copy
import re
import bleach
from fastapi import HTTPException
from sqlalchemy import select, update
from app.core.permissions import ROLES
from app.core.config import settings
from app.db.models import Audit, Document, Record
from app.services.seed import DEFAULTS

CONTENT = {'posts','gallery','media','vendors','landing'}
OPERATIONS = {'teams','fixtures'}

def document(db, key):
    row = db.get(Document, key)
    return copy.deepcopy(row.value) if row else copy.deepcopy(DEFAULTS.get(key, []))

def reserve(db, key, revision=None):
    row = db.get(Document, key)
    if row is None: raise HTTPException(404, 'Unknown resource')
    if revision is not None and row.revision != revision:
        raise HTTPException(409, 'This data changed in another session. Reload this page and apply your changes again.')
    expected = row.revision if revision is None else revision
    result = db.execute(update(Document).where(Document.key == key, Document.revision == expected).values(revision=Document.revision + 1))
    if result.rowcount != 1: raise HTTPException(409, 'This data changed in another session. Reload this page and apply your changes again.')
    db.flush()

def lock_operations(db):
    # A shared write lock serialises cross-resource capacity and fixture invariants.
    db.execute(update(Document).where(Document.key == '_operations').values(revision=Document.revision + 1))
    db.flush()

def snapshot(db, user=None):
    permissions = ROLES.get(user.role, set()) if user else set()
    result, revisions = {}, {}
    for row in db.scalars(select(Document)).all():
        key = row.key
        if key.startswith('_') or key in ('teamRegs','vendorRegs'): continue
        value = copy.deepcopy(row.value)
        if key == 'media' and 'content:read' not in permissions: value = []
        if key == 'posts' and 'content:read' not in permissions: value = [x for x in value if x.get('status') == 'Published']
        if key in ('vendors','gallery') and 'content:read' not in permissions: value = [x for x in value if x.get('visible')]
        result[key] = value; revisions[key] = row.revision
    if 'operations:read' in permissions:
        for key in ('teamRegs','vendorRegs'):
            result[key] = [r.value for r in db.scalars(select(Record).where(Record.collection == key)).all()]
            revisions[key] = db.get(Document,key).revision
    if 'logs:read' in permissions:
        from datetime import datetime, timezone
        result['activity'] = [{'id':r.id,'message':r.message,'createdAt':datetime.fromtimestamp(r.created,timezone.utc).isoformat()} for r in db.scalars(select(Audit).order_by(Audit.created.desc()).limit(8))]
    result['uploadPolicy'] = {'proof': {'maxSizeBytes':settings.max_document_size_mb*1024*1024,'types':settings.proof_types},'image':{'maxSizeBytes':settings.max_branding_image_size_mb*1024*1024,'types':settings.image_types}}
    return {'data': result, 'revisions': revisions}

def validate_content(key, value):
    if key in ('settings','landing'):
        if not isinstance(value, dict): raise HTTPException(422, 'Expected an object')
    else:
        if not isinstance(value,list) or any(not isinstance(x,dict) for x in value): raise HTTPException(422, 'Expected a list of objects')
        ids = [x.get('id') for x in value]
        if any(not isinstance(x,str) or not x or len(x)>80 for x in ids) or len(set(ids)) != len(ids): raise HTTPException(422, 'Each item needs a unique ID')
    if key == 'posts':
        slugs = []
        for post in value:
            if post.get('status') not in ('Draft','Published'): raise HTTPException(422, 'Invalid article status')
            if post['status'] == 'Published' and (any(not str(post.get(f,'')).strip() for f in ('title','slug','excerpt','content','date')) or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',post['slug'])):
                raise HTTPException(422,'Published articles require a title, slug, excerpt, content and date')
            if post.get('slug') in slugs: raise HTTPException(409, 'Article slug already exists')
            if post.get('slug'): slugs.append(post['slug'])
            post['content'] = bleach.clean(post.get('content',''), tags=['p','br','div','h2','h3','strong','b','em','i','u','ul','ol','li','blockquote','a','figure','img','figcaption'], attributes={'a':['href','rel'],'img':['src','alt']}, protocols=['http','https','mailto'], strip=True)
    if key == 'settings':
        for field in ['prize','numberOfTeams','affiliationFee','spotBookingFee','vendorStallFee','vendorFoodStallFee']:
            if field in value and (isinstance(value[field],bool) or not isinstance(value[field],(int,float)) or value[field] < (2 if field == 'numberOfTeams' else 0)):
                raise HTTPException(422, f'Invalid {field}')
        if 'numberOfTeams' in value and int(value['numberOfTeams']) != value['numberOfTeams']: raise HTTPException(422,'Capacity must be a whole number')
        if 'lifecycle' in value and value['lifecycle'] not in ['Pre Tournament','Matchday','Completed']: raise HTTPException(422,'Invalid tournament mode')
        if 'modules' in value and (not isinstance(value['modules'],dict) or any(type(v) is not bool for v in value['modules'].values())): raise HTTPException(422,'Module flags must be booleans')
    return value
