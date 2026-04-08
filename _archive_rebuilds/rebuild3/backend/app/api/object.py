from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.common import fetch_all, fetch_one, now_iso, safe_int, ttl_cache
from app.api.object_common import (
    OBJECT_CONFIG,
    build_filters,
    profile_join_sql,
    require_object_type,
    select_fields,
    serialize_row,
)

router = APIRouter(prefix='/api/v1/objects', tags=['objects'])


@router.get('/summary')
@ttl_cache(ttl_seconds=30)
def get_objects_summary(object_type: str = Query(default='cell')):
    require_object_type(object_type)
    table_name = OBJECT_CONFIG[object_type]['table']
    row = fetch_one(
        f"""
        SELECT
          count(*)::bigint AS total_count,
          count(*) FILTER (WHERE lifecycle_state = 'active')::bigint AS active_count,
          count(*) FILTER (WHERE health_state = 'healthy')::bigint AS healthy_count,
          count(*) FILTER (WHERE anchorable)::bigint AS anchorable_count,
          count(*) FILTER (WHERE baseline_eligible)::bigint AS baseline_count,
          count(*) FILTER (WHERE lifecycle_state = 'active' AND health_state <> 'healthy')::bigint AS watch_count
        FROM {table_name}
        """
    )
    lifecycle = fetch_all(
        f"SELECT lifecycle_state AS label, count(*)::bigint AS count FROM {table_name} GROUP BY lifecycle_state ORDER BY count DESC"
    )
    health = fetch_all(
        f"SELECT health_state AS label, count(*)::bigint AS count FROM {table_name} GROUP BY health_state ORDER BY count DESC"
    )
    r3_only = fetch_one(
        f"""
        SELECT count(*)::bigint AS cnt
        FROM {table_name} o
        LEFT JOIN {OBJECT_CONFIG[object_type]['compare_table']} c ON c.object_id = o.object_id
        WHERE o.baseline_eligible AND NOT coalesce(c.baseline_eligible, false)
        """
    )
    return {
        'status': 'ok',
        'generated_at': now_iso(),
        'object_type': object_type,
        'summary': {
            'total': safe_int(row.get('total_count')),
            'active': safe_int(row.get('active_count')),
            'healthy': safe_int(row.get('healthy_count')),
            'anchorable': safe_int(row.get('anchorable_count')),
            'baseline_eligible': safe_int(row.get('baseline_count')),
            'watch': safe_int(row.get('watch_count')),
            'r3_only': safe_int(r3_only.get('cnt')),
            'lifecycle': [{'label': item['label'], 'count': safe_int(item['count'])} for item in lifecycle],
            'health': [{'label': item['label'], 'count': safe_int(item['count'])} for item in health],
        },
    }


@router.get('/list')
def get_objects_list(
    object_type: str = Query(default='cell'),
    query: str | None = Query(default=None),
    operator_code: str | None = Query(default='all'),
    tech_norm: str | None = Query(default='all'),
    lifecycle_state: str | None = Query(default='all'),
    health_state: str | None = Query(default='all'),
    qualification: str | None = Query(default='all'),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=10, le=100),
    sort_by: str = Query(default='record_count'),
    sort_dir: str = Query(default='desc'),
):
    config = require_object_type(object_type)
    where, params = build_filters(object_type, query, operator_code, tech_norm, lifecycle_state, health_state, qualification)
    params['limit'] = page_size
    params['offset'] = (page - 1) * page_size
    sort_column = config['sort_map'].get(sort_by, list(config['sort_map'].values())[0])
    sort_direction = 'ASC' if sort_dir.lower() == 'asc' else 'DESC'
    where_clause = ' AND '.join(where)
    total_row = fetch_one(
        f"""
        SELECT count(*)::bigint AS total_count
        FROM {config['table']} o
        WHERE {where_clause}
        """,
        params,
    )
    total = safe_int(total_row.get('total_count'))
    sql = f"""
    WITH page_rows AS (
      SELECT *
      FROM {config['table']} o
      WHERE {where_clause}
      ORDER BY {sort_column} {sort_direction}, object_id ASC
      LIMIT %(limit)s OFFSET %(offset)s
    )
    SELECT {select_fields(object_type, include_total=False)}
    FROM page_rows o
    {profile_join_sql(object_type)}
    ORDER BY {sort_column} {sort_direction}, object_id ASC
    """
    rows = fetch_all(sql, params)
    return {
        'status': 'ok',
        'generated_at': now_iso(),
        'object_type': object_type,
        'rows': [serialize_row(object_type, row) for row in rows],
        'page': page,
        'page_size': page_size,
        'total': total,
        'total_pages': max(1, (total + page_size - 1) // page_size),
    }


@router.get('/profile-list')
def get_profile_list(
    object_type: str = Query(default='cell'),
    query: str | None = Query(default=None),
    operator_code: str | None = Query(default='all'),
    tech_norm: str | None = Query(default='all'),
    health_state: str | None = Query(default='all'),
    qualification: str | None = Query(default='all'),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=10, le=100),
):
    data = get_objects_list(
        object_type=object_type,
        query=query,
        operator_code=operator_code,
        tech_norm=tech_norm,
        lifecycle_state='all',
        health_state=health_state,
        qualification=qualification,
        page=page,
        page_size=page_size,
        sort_by='record_count',
        sort_dir='desc',
    )
    summary = get_objects_summary(object_type=object_type)
    return {
        'status': 'ok',
        'generated_at': now_iso(),
        'object_type': object_type,
        'summary': summary['summary'],
        'rows': data['rows'],
        'page': data['page'],
        'page_size': data['page_size'],
        'total': data['total'],
        'total_pages': data['total_pages'],
        'notes': [
            '画像页以统一主状态为主，旧分类 / 旧可信度降级为解释层。',
            'Cell / BS / LAC 使用同一组 health_state 枚举。',
        ],
    }
