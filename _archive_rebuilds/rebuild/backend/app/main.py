"""WangYou Data Governance Workbench — FastAPI Application."""

from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.api import metrics, pipeline, runs, source_fields, steps, workbench

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"

app = FastAPI(
    title=settings.app_title,
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(pipeline.router, prefix="/api/v1")
app.include_router(runs.router, prefix="/api/v1")
app.include_router(steps.router, prefix="/api/v1")
app.include_router(metrics.router, prefix="/api/v1")
app.include_router(workbench.router, prefix="/api/v1")
app.include_router(source_fields.router, prefix="/api/v1")


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "detail": str(exc),
            "error_type": exc.__class__.__name__,
        },
    )


@app.get("/api/v1/health")
async def health_check():
    return {"status": "ok", "version": "0.1.0"}


if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
