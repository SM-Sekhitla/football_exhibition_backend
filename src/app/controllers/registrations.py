from datetime import datetime, timezone
from uuid import uuid4
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from app.api.deps import DB, require
from app.db.models import Document, Record, User
from app.schemas.registration import Lookup, Review, TeamApplication, VendorApplication
from app.services.audit import audit
from app.services.content import document, lock_operations, reserve, snapshot
from app.services.email import enqueue_email
from app.services.email_templates import application_email, submission_email
from app.services.storage import save_upload


def notify_admins(db, kind, value):
    text, html = submission_email(kind, value, db)
    recipients = db.scalars(select(User.email).where(User.active.is_(True), User.role.in_(['admin', 'super_admin']))).all()
    for recipient in sorted(set(email.lower() for email in recipients)):
        enqueue_email(db, recipient, f'BEST5 new {kind} submission — {value["id"]}', text, html)


def create_team(body: TeamApplication, db: DB, request: Request):
    lock_operations(db)
    settings = document(db,'settings')
    if not settings['modules']['teamRegistration'] or settings['lifecycle'] != 'Pre Tournament': raise HTTPException(409,'Team registration is closed')
    approved = db.scalars(select(Record).where(Record.collection == 'teamRegs')).all()
    if sum(r.value['status']=='Approved' for r in approved) >= settings['numberOfTeams']: raise HTTPException(409,'All tournament places are filled')
    identity = body.teamName.casefold()
    if db.scalar(select(Record).where(Record.collection=='teamRegs', Record.identity==identity)): raise HTTPException(409,'An application already exists for this team. Contact the organiser if you need help.')
    identifier = 'B5-' + uuid4().hex[:12].upper()
    logo = save_upload(db, body.logo.name, body.logo.type, body.logo.data, owner=identifier)['src']
    proof = save_upload(db, body.proofOfPayment.name, body.proofOfPayment.type, body.proofOfPayment.data, private=True, owner=identifier)
    value = body.model_dump(exclude={'proofOfPayment','prerequisitesAccepted','logo'})
    value.update(logo=logo, id=identifier, email=str(body.email).lower(), submitted=datetime.now(timezone.utc).isoformat(), status='Pending', paymentStatus='Under review', proofOfPayment={k:proof[k] for k in ('id','name','type','data')}, prerequisitesAcceptedAt=datetime.now(timezone.utc).isoformat(), prerequisitesVersion=db.get(Document,'settings').revision)
    db.add(Record(id=identifier, collection='teamRegs', identity=identity, value=value))
    reserve(db,'teamRegs'); audit(db,'registrations','Team application submitted',request_id=request.state.request_id)
    text,html=application_email('team',value['teamName'],identifier,db)
    enqueue_email(db,value['email'],'BEST5 team application received',text,html)
    notify_admins(db,'team',value)
    db.commit()
    return {'id':identifier, 'status':'Pending','paymentStatus':'Under review'}


def create_vendor(body: VendorApplication, db: DB, request: Request):
    lock_operations(db)
    settings=document(db,'settings')
    if not settings['modules']['vendorRegistration']: raise HTTPException(409,'Vendor registration is closed')
    fee=settings.get('vendorFoodStallFee',1000) if body.category.strip().casefold()=='food & drinks' else settings.get('vendorStallFee',350)
    identifier = 'B5-' + uuid4().hex[:12].upper()
    identity = body.business.casefold()
    if db.scalar(select(Record).where(Record.collection=='vendorRegs',Record.identity==identity)): raise HTTPException(409,'An application already exists for this business')
    value = body.model_dump(); value.update(id=identifier,email=str(body.email).lower(),submitted=datetime.now(timezone.utc).isoformat(),status='Pending',paymentStatus='Awaiting payment',stallFee=fee)
    db.add(Record(id=identifier,collection='vendorRegs',identity=identity,value=value)); reserve(db,'vendorRegs')
    text,html=application_email('vendor',value['business'],identifier,db,stall_fee=fee)
    enqueue_email(db,value['email'],'BEST5 vendor application received',text,html)
    notify_admins(db,'vendor',value)
    audit(db,'registrations','Vendor application submitted',request_id=request.state.request_id); db.commit()
    return {'id':identifier,'status':'Pending','paymentStatus':'Awaiting payment','stallFee':fee}


def lookup(body: Lookup, db: DB):
    record = db.get(Record, body.reference.strip().upper())
    if not record or record.value['email'].lower() != str(body.email).lower(): raise HTTPException(404,'No application matches this reference and email')
    # Never expose proof data or other application PII through public lookup.
    return {k:v for k,v in record.value.items() if k in ('id','teamName','business','status','paymentStatus','reviewNote','stallFee')}


def review(kind: str, identifier: str, body: Review, db: DB, request: Request, user=Depends(require('operations:write'))):
    if kind not in ('team','vendor'): raise HTTPException(404,'Unknown application type')
    lock_operations(db)  # Serialise capacity checks and team promotions across workers.
    key = 'teamRegs' if kind == 'team' else 'vendorRegs'
    reserve(db,key)
    row = db.get(Record,identifier)
    if not row or row.collection != key: raise HTTPException(404,'Application not found')
    value = dict(row.value)
    if body.status == 'Rejected' and not body.reviewNote: raise HTTPException(422,'Add a reason for rejecting this application')
    if kind == 'team':
        teams = document(db,'teams'); team_id = value.get('officialTeamId')
        if body.status == 'Approved':
            if body.paymentStatus != 'Verified': raise HTTPException(422,'Verify the spot booking payment before approving the team')
            if not any(t['id'] == team_id for t in teams):
                if len(teams) >= document(db,'settings')['numberOfTeams']: raise HTTPException(409,'Tournament capacity reached')
                team_id = str(uuid4())
                teams.append({'id':team_id,'name':value['teamName'],'short':''.join(n[0] for n in value['teamName'].split())[:3].upper(),'captain':value['captain'],'city':value['city'],'group':'Unassigned','logo':value.get('logo') or '','players':[{'id':f'{team_id}-{i}','name':n,'number':i+1,'position':'GK' if i==0 else 'FW'} for i,n in enumerate(value['players'])]})
                value['officialTeamId'] = team_id
        elif team_id:
            if any(team_id in (f['homeId'],f['awayId']) for f in document(db,'fixtures')): raise HTTPException(409,'Remove this team from fixtures before reversing approval')
            teams = [t for t in teams if t['id'] != team_id]; value.pop('officialTeamId',None)
        reserve(db,'teams'); db.get(Document,'teams').value = teams
    previous = {k:value.get(k) for k in ('status','paymentStatus','reviewNote')}
    value.update(body.model_dump()); row.value = value
    if previous != body.model_dump():
        enqueue_email(db,value['email'],'BEST5 application update',f'Application {identifier}: {body.status}. Payment: {body.paymentStatus}.\n{body.reviewNote}')
    audit(db,'registrations',f'Application {identifier} reviewed: {body.status}',user.id,request.state.request_id); db.commit()
    return snapshot(db,user)
