"""Routing Step 2 routes for rb5."""
from __future__ import annotations

from fastapi import APIRouter

from ..core.envelope import success_envelope
from ..profile.pipeline import run_profile_pipeline
from ..profile.queries import get_routing_payload


router = APIRouter(prefix='/api/routing', tags=['routing'])


@router.post('/run')
def run_routing() -> dict[str, object]:
    return success_envelope(run_profile_pipeline())


@router.get('/stats')
def get_routing_stats() -> dict[str, object]:
    return success_envelope(get_routing_payload())
