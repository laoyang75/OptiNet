"""rebuild4 流式治理工作台 - FastAPI Backend."""
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import flow, runs, objects, workspaces, baseline, profiles, governance, compare, governance_foundation

app = FastAPI(title="rebuild4 流式治理工作台", version="1.0.0")

FRONTEND_PORT = os.getenv("REBUILD4_FRONTEND_PORT", "47132")
FRONTEND_HOST = os.getenv("REBUILD4_FRONTEND_HOST", "127.0.0.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        f"http://{FRONTEND_HOST}:{FRONTEND_PORT}",
        f"http://localhost:{FRONTEND_PORT}",
        "http://127.0.0.1:47132",
        "http://localhost:47132",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(flow.router)
app.include_router(runs.router)
app.include_router(objects.router)
app.include_router(workspaces.router)
app.include_router(baseline.router)
app.include_router(profiles.router)
app.include_router(governance.router)
app.include_router(compare.router)
app.include_router(governance_foundation.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "rebuild4-backend"}


@app.get("/api/system/status")
def system_status():
    from .core.database import fetchone
    from .core.context import get_current_pointer
    cp = get_current_pointer()
    if not cp:
        return {"status": "idle", "mode": None}

    # check if any batch is processing
    processing = fetchone("""
        SELECT COUNT(*) as cnt FROM rebuild4_meta.batch
        WHERE status = 'processing'
    """)

    gate_status = fetchone("""
        SELECT gate_code, status FROM rebuild4_meta.gate_run_result
        WHERE gate_code IN ('G4','G5','G6','G7','G8') AND status = 'running'
        ORDER BY gate_code LIMIT 1
    """)

    if processing and int(processing["cnt"]) > 0:
        return {"status": "processing", "mode": "batch_processing"}
    if gate_status:
        return {"status": "validation", "mode": "validation", "gate": gate_status["gate_code"]}
    return {"status": "normal", "mode": None, "current_run_id": cp["current_run_id"],
            "current_batch_id": cp["current_batch_id"]}
