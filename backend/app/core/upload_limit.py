from starlette.responses import JSONResponse
from app.core.config import settings

class UploadLimit:
    """Bound multipart bytes before Starlette parses/spools the request."""
    def __init__(self, app):
        self.app=app

    async def __call__(self,scope,receive,send):
        if scope['type']!='http' or scope['method']!='POST' or scope['path'] not in {'/api/documents/upload','/api/batches/upload'}:
            return await self.app(scope,receive,send)
        messages=[];total=0
        while True:
            message=await receive()
            if message['type']=='http.disconnect':
                return
            total+=len(message.get('body',b''))
            if total>settings.max_request_bytes:
                return await JSONResponse({'detail':'Upload request exceeds size limit'},status_code=413)(scope,receive,send)
            messages.append(message)
            if not message.get('more_body',False):
                break
        iterator=iter(messages)
        async def replay():
            try:
                return next(iterator)
            except StopIteration:
                return await receive()
        await self.app(scope,replay,send)
