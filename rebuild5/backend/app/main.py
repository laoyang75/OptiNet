"""rebuild5 FastAPI application."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.envelope import success_envelope
from .core.settings import settings
from .routers.evaluation import router as evaluation_router
from .routers.enrichment import router as enrichment_router
from .routers.maintenance import router as maintenance_router
from .routers.service import router as service_router
from .routers.system import router as system_router, pipeline_router
from .routers.etl import router as etl_router
from .routers.profile import router as routing_router


app = FastAPI(title="rebuild5 backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        f"http://{settings.frontend_host}:{settings.frontend_port}",
        f"http://localhost:{settings.frontend_port}",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/system/health")
def health() -> dict[str, object]:
    return success_envelope(
        {"status": "ok", "service": "rebuild5-backend"},
        meta={"service": "rebuild5", "version": "0.1.0"},
    )


app.include_router(system_router)
app.include_router(pipeline_router)

app.include_router(etl_router)
app.include_router(routing_router)
app.include_router(evaluation_router)
app.include_router(enrichment_router)
app.include_router(maintenance_router)
app.include_router(service_router)
