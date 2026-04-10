"""System routes for rebuild5."""
from __future__ import annotations

from fastapi import APIRouter, Query

from ..core.envelope import success_envelope
from ..services.system import get_system_config, list_run_logs
from ..etl.source_prep import prepare_current_dataset


router = APIRouter(prefix="/api/system", tags=["system"])

pipeline_router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])


@router.get('/config')
def get_config() -> dict[str, object]:
    return success_envelope(get_system_config(), meta={"service": "rebuild5"})


@router.get('/run-log')
def get_run_log() -> dict[str, object]:
    return success_envelope({"runs": list_run_logs()}, meta={"service": "rebuild5"})


@router.post('/prepare-current-dataset')
def prepare_dataset() -> dict[str, object]:
    """Prepare the single active dataset defined in ``config/dataset.yaml``."""
    return success_envelope(prepare_current_dataset())


@router.post('/prepare-sample')
def prepare_sample() -> dict[str, object]:
    """Deprecated alias kept for backward compatibility with older scripts."""
    return success_envelope(prepare_current_dataset())


@pipeline_router.post('/run')
def run_pipeline(from_step: int = Query(1, ge=1, le=5)) -> dict[str, object]:
    """Run pipeline from a given step.

    from_step=1: full pipeline (Step 1-5)
    from_step=2: rerun Step 2-5 (after parameter changes)
    from_step=5: rerun Step 5 only (maintenance)
    """
    from ..etl.pipeline import run_step1_pipeline
    from ..profile.pipeline import run_profile_pipeline
    from ..enrichment.pipeline import run_enrichment_pipeline
    from ..maintenance.pipeline import run_maintenance_pipeline

    results: dict[str, object] = {}
    if from_step <= 1:
        results['step1'] = run_step1_pipeline()
    if from_step <= 3:
        results['step2_step3'] = run_profile_pipeline()
    if from_step <= 4:
        results['step4'] = run_enrichment_pipeline()
    results['step5'] = run_maintenance_pipeline()
    return success_envelope(results)
