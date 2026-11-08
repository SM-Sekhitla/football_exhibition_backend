import time
from collections import defaultdict, deque
from threading import Lock
from uuid import uuid4
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.config import settings
from app.core.logging import logger

MAX_BODY = max(30 * 1024 * 1024, (settings.max_document_size_mb + settings.max_branding_image_size_mb) * 1024 * 1024 * 4 // 3 + 2 * 1024 * 1024)

class SecurityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.buckets=defaultdict(deque)
        self.lock=Lock()

    async def dispatch(self, request, call_next):
        request.state.request_id=str(uuid4())
        started=time.monotonic()
        origin=request.headers.get('origin')
        response=None
        if request.method not in ('GET','HEAD','OPTIONS'):
            if origin and origin not in settings.cors_origins:
                response=JSONResponse({'detail':'Origin not allowed'},403)
            elif not request.headers.get('content-type','').startswith('application/json'):
                response=JSONResponse({'detail':'Use application/json'},415)
        if settings.rate_limit_enabled and response is None:
            path=request.url.path
            sensitive=any(x in path for x in ('/auth/login','/auth/forgot-password','/auth/reset-password','/auth/accept-invitation','/invitation','/banking'))
            public_submit=path.startswith(settings.api_v1_prefix+'/registrations') and request.method=='POST'
            category='auth' if sensitive else 'registration' if public_submit else 'api'
            limit=10 if sensitive else 30 if public_submit else 600
            key=(request.client.host if request.client else 'unknown',category)
            with self.lock:
                cutoff=time.monotonic()-60
                for stale in list(self.buckets):
                    if not self.buckets[stale] or self.buckets[stale][-1]<cutoff: del self.buckets[stale]
                bucket=self.buckets[key]
                while bucket and bucket[0]<cutoff: bucket.popleft()
                if len(bucket)>=limit: response=JSONResponse({'detail':'Too many requests. Try again in a minute.'},429,headers={'Retry-After':'60'})
                else: bucket.append(time.monotonic())
        # Bound streamed/chunked bodies as well as Content-Length requests.
        if response is None and request.method in ('POST','PUT','PATCH'):
            body=bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body)>MAX_BODY:
                    response=JSONResponse({'detail':'Request is too large'},413); break
            if response is None:
                request._body=bytes(body)
        if response is None:
            try: response=await call_next(request)
            except Exception as exc:
                logger.error('Unhandled request error request=%s path=%s type=%s',request.state.request_id,request.url.path,type(exc).__name__)
                response=JSONResponse({'detail':'An unexpected server error occurred','requestId':request.state.request_id},500)
        response.headers.update({'X-Request-ID':request.state.request_id,'X-Content-Type-Options':'nosniff','X-Frame-Options':'DENY','Referrer-Policy':'strict-origin-when-cross-origin','Permissions-Policy':'camera=(), microphone=(), geolocation=()'})
        if not request.url.path.startswith(settings.api_v1_prefix+'/files/'): response.headers['Cache-Control']='no-store'
        if settings.secure_cookies: response.headers['Strict-Transport-Security']='max-age=31536000; includeSubDomains'
        # No query string, headers, request bodies or credentials in request logs.
        logger.info('request=%s method=%s path=%s status=%s duration_ms=%d',request.state.request_id,request.method,request.url.path,response.status_code,(time.monotonic()-started)*1000)
        return response
