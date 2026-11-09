import copy
import re
from datetime import datetime
from fastapi import Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy import select
from app.api.deps import DB, require
from app.core.config import ROOT, settings
from app.core.security import verify_password
from app.db.models import Document, Record, Upload
from app.schemas.registration import BankingUpdate
from app.services.audit import audit
from app.services.content import CONTENT, OPERATIONS, document, lock_operations, reserve, snapshot, validate_content
from app.services.storage import save_upload


def public_bootstrap(db: DB):
    return snapshot(db)


def admin_bootstrap(db: DB, user=Depends(require('content:read'))):
    return snapshot(db,user)


def persist_images(db, value):
    if isinstance(value,dict): return {k:persist_images(db,v) for k,v in value.items()}
    if isinstance(value,list): return [persist_images(db,v) for v in value]
    if isinstance(value,str) and value.startswith('data:image/'):
        mime = value.split(';',1)[0][5:]
        if mime not in ('image/png','image/jpeg','image/webp','image/gif','image/avif'): raise HTTPException(422,'Unsupported image format')
        return save_upload(db,'image',mime,value)['src']
    return value


def validate_fixtures(db, fixtures):
    teams = {t['id']:t for t in document(db,'teams')}
    slots = []
    for f in fixtures:
        if any(key not in f for key in ('homeId','awayId','date','time','pitch','stage','group','status')): raise HTTPException(422,'Incomplete fixture')
        if f['homeId'] not in teams or f['awayId'] not in teams or f['homeId']==f['awayId']: raise HTTPException(422,'Choose two different official teams')
        if f['status'] not in ('Upcoming','Live','Half Time','Full Time','Cancelled'): raise HTTPException(422,'Invalid fixture status')
        if f['stage'] not in ('Group Stage','Quarter Final','Semi Final','Final'): raise HTTPException(422,'Invalid fixture stage')
        if f['stage']=='Group Stage' and any(teams[x]['group']!=f['group'] for x in (f['homeId'],f['awayId'])): raise HTTPException(422,'Both teams must belong to the fixture group')
        if f['stage']!='Group Stage' and f['group']!='Knockout': raise HTTPException(422,'Knockout games must use the Knockout group')
        try:
            day = datetime.fromisoformat(f['date']).date() if re.match(r'^\d{4}-',f['date']) else datetime.strptime(f['date'],'%d %b %Y').date()
            datetime.strptime(f['time'],'%H:%M')
        except (ValueError,TypeError): raise HTTPException(422,'Invalid fixture date or time')
        if not str(f['pitch']).strip(): raise HTTPException(422,'Pitch is required')
        for key in ('homeScore','awayScore'):
            score=f.get(key)
            if score is not None and (type(score) is not int or score<0): raise HTTPException(422,'Scores must be non-negative integers')
        if f['status']=='Full Time' and any(f.get(k) is None for k in ('homeScore','awayScore')): raise HTTPException(422,'Completed matches require both scores')
        if f['status']=='Upcoming': f.pop('homeScore',None); f.pop('awayScore',None)
        if f['status']=='Cancelled': continue
        for other_day,other in slots:
            if day==other_day and f['time']==other['time'] and (f['pitch'].strip().casefold()==other['pitch'].strip().casefold() or set([f['homeId'],f['awayId']]) & set([other['homeId'],other['awayId']])): raise HTTPException(409,'A team or pitch is already scheduled at this time')
        slots.append((day,f))


def save_document(key: str, request: Request, db: DB, payload: dict, user=Depends(require('content:write'))):
    # Route wrapper selects the required permission dynamically; never trust client role data.
    return save_document_for_user(key,request,db,payload,user)


def save_document_for_user(key,request,db,payload,user):
    from app.core.permissions import ROLES
    if key not in CONTENT | OPERATIONS | {'settings'}: raise HTTPException(404,'Unknown resource')
    permission = 'content:write' if key in CONTENT else 'operations:write' if key in OPERATIONS else 'settings:write'
    if permission not in ROLES.get(user.role,set()): raise HTTPException(403,'You do not have permission for this action')
    revision = payload.get('revision')
    if type(revision) is not int or 'value' not in payload: raise HTTPException(422,'A resource revision and value are required')
    incoming = copy.deepcopy(payload['value'])
    if key in ('settings','landing') and isinstance(incoming,dict):
        incoming = {**document(db,key),**incoming}
    from pydantic import TypeAdapter, ValidationError
    from app.schemas.content import Fixture, Gallery, Landing, Media, Post, SettingsSchema, Team, Vendor
    schema = {'settings':SettingsSchema,'landing':Landing,'teams':list[Team],'fixtures':list[Fixture],'posts':list[Post],'gallery':list[Gallery],'media':list[Media],'vendors':list[Vendor]}[key]
    try:
        incoming = TypeAdapter(schema).validate_python(incoming)
        incoming = TypeAdapter(schema).dump_python(incoming,mode='json',exclude_none=True)
    except ValidationError as exc:
        raise HTTPException(422,'; '.join(f'{".".join(map(str,e["loc"]))}: {e["msg"]}' for e in exc.errors()))
    value = validate_content(key,incoming)
    if key in ('settings','teams','fixtures'): lock_operations(db)
    reserve(db,key,revision)
    if key == 'settings':
        old = document(db,key)
        if value.get('banking',old['banking']) != old['banking']: raise HTTPException(403,'Use the password-protected banking update')
        if set(value)-set(old): raise HTTPException(422,'Unknown setting')
        if value.get('numberOfTeams',old['numberOfTeams']) < len(document(db,'teams')): raise HTTPException(409,'Capacity cannot be less than the current team count')
        value = {**old,**value}
    if key == 'landing':
        # The validated Landing schema defines allowed fields. Older saved documents
        # may predate sponsorLogos and must accept newly supported fields.
        value = {**document(db,key),**value}
    if key == 'teams':
        old = {t['id']:t for t in document(db,'teams')}
        if set(t['id'] for t in value) != set(old): raise HTTPException(403,'Teams are created through application approval and removed individually')
        for team in value:
            previous = old[team['id']]
            if any(v!=previous.get(k) for k,v in team.items() if k!='group') or set(team)!=set(previous): raise HTTPException(422,'Only group assignment can be edited here')
            if team.get('group') not in ('Unassigned','Group A','Group B','Group C','Group D'): raise HTTPException(422,'Invalid team group')
        # Group changes cannot invalidate already scheduled matches.
        db.get(Document,key).value = value
        validate_fixtures(db,document(db,'fixtures'))
    if key == 'fixtures':
        validate_fixtures(db,value)
    if key == 'posts':
        # Optimised editor images embedded in HTML are persisted as public assets.
        for post in value:
            def replace_image(match):
                return persist_images(db,match.group(0))
            post['content'] = re.sub(r'data:image/(?:png|jpeg|webp|gif|avif);base64,[A-Za-z0-9+/=]+', replace_image,post.get('content',''))
    value = persist_images(db,value)
    db.get(Document,key).value = value
    audit(db,'content' if key in CONTENT else key,f'{key} updated',user.id,request.state.request_id); db.commit()
    return snapshot(db,user)


def banking(body: BankingUpdate, request: Request, db: DB, user=Depends(require('banking:write'))):
    if not verify_password(body.password,user.password_hash):
        audit(db,'security','Banking update rejected: password check failed',user.id,request.state.request_id,level='WARNING'); db.commit()
        raise HTTPException(403,'Incorrect admin password. Banking details were not changed.')
    lock_operations(db); reserve(db,'settings')
    value = document(db,'settings'); value['banking'] = body.banking.model_dump()
    db.get(Document,'settings').value = value
    audit(db,'banking','Banking details changed after password confirmation',user.id,request.state.request_id); db.commit()
    return snapshot(db,user)


def remove_team(identifier: str, request: Request, db: DB, user=Depends(require('operations:write'))):
    lock_operations(db); reserve(db,'teams')
    if any(identifier in (f['homeId'],f['awayId']) for f in document(db,'fixtures')): raise HTTPException(409,'Remove this team from fixtures before removing it')
    teams = document(db,'teams')
    if not any(t['id']==identifier for t in teams): raise HTTPException(404,'Team not found')
    db.get(Document,'teams').value = [t for t in teams if t['id']!=identifier]
    for row in db.scalars(select(Record).where(Record.collection=='teamRegs')):
        if row.value.get('officialTeamId')==identifier:
            value=dict(row.value); value.pop('officialTeamId',None); value['status']='Pending'; row.value=value
    reserve(db,'teamRegs'); audit(db,'teams','Official team removed; application returned to pending',user.id,request.state.request_id); db.commit()
    return snapshot(db,user)


def download(identifier: str, request: Request, db: DB):
    row=db.get(Upload,identifier)
    if not row: raise HTTPException(404,'File not found')
    if row.private:
        from app.api.deps import current_user
        user=current_user(request,db)
        from app.core.permissions import ROLES
        if user.must_change_password or 'operations:read' not in ROLES.get(user.role,set()): raise HTTPException(403,'You cannot access payment proofs')
        audit(db,'documents','Payment proof downloaded',user.id,request.state.request_id); db.commit()
    directory=settings.storage_dir if row.private else settings.branding_path
    path=directory / row.id
    if not path.is_file(): path=settings.storage_dir / row.id
    if not path.is_file(): path=ROOT / 'data/uploads' / row.id
    if not path.is_file(): raise HTTPException(404,'File unavailable')
    return FileResponse(path,media_type=row.mime,filename=row.name,content_disposition_type='attachment' if row.private else 'inline',headers={'Cache-Control':'private, no-store' if row.private else 'public, max-age=86400','X-Content-Type-Options':'nosniff'})
