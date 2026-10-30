from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from app.api import auth, future, knowledge, company
from app.core.upload_limit import UploadLimit
from app.core.config import settings
from app.core.database import initialize, connection

@asynccontextmanager
async def lifespan(app):
    initialize()
    auth.provision_admins()
    # Single-worker local service: recover interrupted ingestion on startup.
    with connection() as db:
        db.execute("UPDATE documents SET processing_status='failed',error='Interrupted processing; retry the upload' WHERE processing_status='processing'")
    yield

app = FastAPI(title='Enterprise Knowledge AI', version='0.3.0', lifespan=lifespan)

@app.middleware('http')
async def origin_guard(request: Request, call_next):
    if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'}:
        origin = request.headers.get('origin')
        if (origin and origin not in settings.allowed_origins.split(',')) or request.headers.get('sec-fetch-site') == 'cross-site':
            return JSONResponse({'detail': 'Origin not allowed'}, status_code=403)
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response

@app.get('/api/health')
def health():
    return {'status': 'ok', 'phase': 3}

app.include_router(auth.router, prefix='/api')
app.include_router(future.router, prefix='/api')

app.include_router(knowledge.router, prefix='/api')
app.include_router(company.router, prefix='/api')
app.add_middleware(UploadLimit)
