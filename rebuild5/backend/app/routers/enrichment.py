"""Step 4 enrichment routes."""
from __future__ import annotations

from fastapi import APIRouter, Query

from ..core.envelope import success_envelope
from ..enrichment.pipeline import run_enrichment_pipeline
from ..enrichment.queries import (
    get_enrichment_anomalies_payload,
    get_enrichment_coverage_payload,
    get_enrichment_stats_payload,
)


router = APIRouter(prefix='/api/enrichment', tags=['enrichment'])


@router.post('/run')
def run_enrichment() -> dict[str, object]:
    return success_envelope(run_enrichment_pipeline())


@router.get('/stats')
def enrichment_stats() -> dict[str, object]:
    return success_envelope(get_enrichment_stats_payload())


@router.get('/coverage')
def enrichment_coverage() -> dict[str, object]:
    return success_envelope(get_enrichment_coverage_payload())


@router.get('/anomalies')
def enrichment_anomalies(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500)) -> dict[str, object]:
    payload = get_enrichment_anomalies_payload(page=page, page_size=page_size)
    page_info = payload.pop('_page_info', None)
    return success_envelope(payload, page_info=page_info)
