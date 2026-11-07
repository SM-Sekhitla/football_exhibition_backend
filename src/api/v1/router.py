from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from src.api.deps import DB, CurrentUser
from src.controllers import admin, auth, content, registrations

router=APIRouter()
router.add_api_route('/auth/login',auth.login,methods=['POST'],tags=['auth'])
router.add_api_route('/auth/me',auth.me,methods=['GET'],tags=['auth'])
router.add_api_route('/auth/logout',auth.logout,methods=['POST'],tags=['auth'])
router.add_api_route('/auth/change-password',auth.change_password,methods=['POST'],tags=['auth'])
router.add_api_route('/auth/forgot-password',auth.forgot_password,methods=['POST'],tags=['auth'])
router.add_api_route('/auth/accept-invitation',auth.accept_invitation,methods=['POST'],tags=['auth'])
router.add_api_route('/auth/reset-password',auth.reset_password,methods=['POST'],tags=['auth'])
router.add_api_route('/public/bootstrap',content.public_bootstrap,methods=['GET'],tags=['public'])

@router.get('/admin/bootstrap',tags=['admin'])
def bootstrap(db: DB,user: CurrentUser):
    if user.must_change_password: return {'data':{},'revisions':{}}
    return content.snapshot(db,user)

@router.put('/admin/content/{key}',tags=['content'])
def save_content(key: str,payload: dict,request: Request,db: DB,user: CurrentUser):
    if user.must_change_password:
        from fastapi import HTTPException
        raise HTTPException(403,'Change your initial password before continuing')
    return content.save_document_for_user(key,request,db,payload,user)

router.add_api_route('/admin/settings/banking',content.banking,methods=['PUT'],tags=['settings'])
router.add_api_route('/admin/teams/{identifier}',content.remove_team,methods=['DELETE'],tags=['operations'])
router.add_api_route('/registrations/team',registrations.create_team,methods=['POST'],status_code=201,tags=['registrations'])
router.add_api_route('/registrations/vendor',registrations.create_vendor,methods=['POST'],status_code=201,tags=['registrations'])
router.add_api_route('/registrations/lookup',registrations.lookup,methods=['POST'],tags=['registrations'])
router.add_api_route('/admin/registrations/{kind}/{identifier}',registrations.review,methods=['PATCH'],tags=['registrations'])
router.add_api_route('/files/{identifier}',content.download,methods=['GET'],tags=['files'])
router.add_api_route('/admin/users',admin.users,methods=['GET'],tags=['users'])
router.add_api_route('/admin/users',admin.create_user,methods=['POST'],status_code=201,tags=['users'])
router.add_api_route('/admin/staff-email-status',admin.staff_email_status,methods=['GET'],tags=['users'])
router.add_api_route('/admin/users/{identifier}/invitation',admin.resend_invitation,methods=['POST'],tags=['users'])
router.add_api_route('/admin/users/{identifier}',admin.update_user,methods=['PATCH'],tags=['users'])
router.add_api_route('/admin/logs',admin.logs,methods=['GET'],tags=['logs'])
router.add_api_route('/admin/request-logs',admin.request_logs,methods=['GET'],tags=['logs'])
router.add_api_route('/admin/email-jobs',admin.email_jobs,methods=['GET'],tags=['email'])
router.add_api_route('/admin/email-jobs/{identifier}/retry',admin.retry_email,methods=['POST'],tags=['email'])

@router.get('/health',tags=['health'])
def health(db: DB):
    db.execute(text('SELECT 1'))
    return {'status':'ok'}
