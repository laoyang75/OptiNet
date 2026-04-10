"""Unified API envelope helpers."""
from __future__ import annotations

from typing import Any


def _default_meta() -> dict[str, Any]:
    from .settings import settings
    return {'dataset_key': settings.dataset_key}


def success_envelope(data: Any, meta: dict[str, Any] | None = None, page_info: dict[str, Any] | None = None) -> dict[str, Any]:
    merged_meta = {**_default_meta(), **(meta or {})}
    if page_info:
        merged_meta = {
            **merged_meta,
            'page': page_info['page'],
            'page_size': page_info['page_size'],
            'total_count': page_info['total_count'],
            'total_pages': page_info['total_pages'],
        }
    return {
        "data": data,
        "meta": merged_meta,
        "error": None,
    }


def error_envelope(code: str, message: str, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "data": None,
        "meta": meta or {},
        "error": {
            "code": code,
            "message": message,
        },
    }
