"""ETL routes for rb5."""
from __future__ import annotations

from fastapi import APIRouter

from ..core.envelope import success_envelope
from ..etl.pipeline import run_step1_pipeline
from ..etl.queries import (
    get_clean_rules_payload,
    get_etl_coverage_payload,
    get_etl_source_payload,
    get_etl_stats_page_payload,
    get_field_audit_payload,
)


router = APIRouter(prefix='/api/etl', tags=['etl'])


@router.post('/run')
def run_etl() -> dict[str, object]:
    return success_envelope(run_step1_pipeline())


@router.get('/source')
def get_source() -> dict[str, object]:
    return success_envelope(get_etl_source_payload())


@router.get('/field-audit')
def get_field_audit() -> dict[str, object]:
    return success_envelope(get_field_audit_payload())


@router.get('/stats')
def get_stats() -> dict[str, object]:
    return success_envelope(get_etl_stats_page_payload())


@router.get('/coverage')
def get_coverage() -> dict[str, object]:
    return success_envelope(get_etl_coverage_payload())


@router.get('/clean-rules')
def get_clean_rules() -> dict[str, object]:
    return success_envelope(get_clean_rules_payload())
