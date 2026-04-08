from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import compare, governance, launcher, object, object_detail, run, run_workspaces
from app.core.config import settings


def allowed_origins() -> list[str]:
    frontend_port = os.environ.get('REBUILD3_FRONTEND_PORT', '47122')
    frontend_host = os.environ.get('REBUILD3_FRONTEND_HOST', '127.0.0.1')
    origins = {
        f'http://{frontend_host}:{frontend_port}',
        f'http://localhost:{frontend_port}',
        'http://127.0.0.1:5173',
        'http://localhost:5173',
    }
    return sorted(origins)

app = FastAPI(title=settings.app_title, version='0.2.0')
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)
app.include_router(run.router)
app.include_router(run_workspaces.router)
app.include_router(object.router)
app.include_router(object_detail.router)
app.include_router(compare.router)
app.include_router(governance.router)
app.include_router(launcher.router)


@app.get('/api/v1/health')
def health():
    return {'status': 'ok', 'project': 'rebuild3', 'version': '0.2.0'}
