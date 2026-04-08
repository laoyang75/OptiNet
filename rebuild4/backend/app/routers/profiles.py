"""API-09: profiles/lac, profiles/bs, profiles/cell."""
from fastapi import APIRouter, Query
from ..core.database import fetchall, fetchone
from ..core.envelope import envelope
from ..core.context import base_context, get_current_baseline_version

router = APIRouter(prefix="/api", tags=["profiles"])


def _profile_ctx(profile_type: str, **filters) -> dict:
    ctx = base_context()
    ctx["profile_type"] = profile_type
    ctx["baseline_version"] = get_current_baseline_version()
    for k, v in filters.items():
        if v is not None:
            ctx[k] = v
    return ctx


# ---------------------------------------------------------------------------
# LAC
# ---------------------------------------------------------------------------
@router.get("/profiles/lac")
def profile_lac(
    q: str = Query(None),
    operator: str = Query(None),
    rat: str = Query(None),
    lifecycle: str = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
):
    ctx = _profile_ctx("lac", filter_operator=operator, filter_rat=rat,
                       filter_lifecycle=lifecycle)
    conditions = ["1=1"]
    params: list = []

    if operator:
        conditions.append("o.operator_code = %s")
        params.append(operator)
    if rat:
        conditions.append("o.tech_norm = %s")
        params.append(rat)
    if lifecycle:
        conditions.append("o.lifecycle_state = %s")
        params.append(lifecycle)
    if q:
        conditions.append("o.lac ILIKE %s")
        params.append(f"%{q}%")

    where = " AND ".join(conditions)
    offset = (page - 1) * size

    rows = fetchall(f"""
        SELECT o.operator_code, o.operator_cn, o.lac, o.tech_norm,
               o.bs_count, o.cell_count, o.record_count, o.total_devices,
               o.active_days, o.independent_obs,
               o.center_lon, o.center_lat,
               ROUND(o.area_km2::numeric, 2) AS area_km2,
               ROUND(o.rsrp_avg::numeric, 1) AS rsrp_avg,
               ROUND(o.gps_original_ratio::numeric, 4) AS gps_original_ratio,
               ROUND(o.signal_original_ratio::numeric, 4) AS signal_original_ratio,
               o.collision_bs_count, o.dynamic_bs_count, o.large_spread_bs_count,
               o.active_bs_count, ROUND(o.anomaly_bs_ratio::numeric, 4) AS anomaly_bs_ratio,
               o.position_grade, o.lifecycle_state,
               o.province_name, o.city_name, o.district_name
        FROM rebuild4.etl_dim_lac o
        WHERE {where}
        ORDER BY o.record_count DESC
        LIMIT %s OFFSET %s
    """, (*params, size, offset))

    total = fetchone(f"SELECT COUNT(*) as cnt FROM rebuild4.etl_dim_lac o WHERE {where}", params)

    summary = fetchone("""
        SELECT COUNT(*) as total,
               COUNT(*) FILTER (WHERE lifecycle_state = 'active') as active,
               COUNT(*) FILTER (WHERE lifecycle_state = 'observing') as observing,
               COUNT(*) FILTER (WHERE lifecycle_state = 'waiting') as waiting,
               COUNT(*) FILTER (WHERE anomaly_bs_ratio > 0) as has_anomaly
        FROM rebuild4.etl_dim_lac
    """)

    return envelope({
        "items": rows,
        "summary": summary or {},
        "total": total["cnt"] if total else 0,
        "page": page, "size": size,
    }, subject_scope="object", subject_note="暂无画像数据" if not rows else None, context=ctx)


# ---------------------------------------------------------------------------
# BS  (data source: etl_dim_bs — aggregated from etl_dim_cell)
# ---------------------------------------------------------------------------
@router.get("/profiles/bs")
def profile_bs(
    q: str = Query(None),
    operator: str = Query(None),
    rat: str = Query(None),
    lac: str = Query(None),
    classification: str = Query(None),
    lifecycle: str = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
):
    ctx = _profile_ctx("bs", filter_operator=operator, filter_rat=rat,
                       filter_lac=lac, filter_classification=classification,
                       filter_lifecycle=lifecycle)
    conditions = ["1=1"]
    params: list = []

    if operator:
        conditions.append("o.operator_code = %s")
        params.append(operator)
    if rat:
        conditions.append("o.tech_norm = %s")
        params.append(rat)
    if lac:
        conditions.append("o.lac = %s")
        params.append(lac)
    if classification:
        conditions.append("o.classification = %s")
        params.append(classification)
    if lifecycle:
        conditions.append("o.lifecycle_state = %s")
        params.append(lifecycle)
    if q:
        conditions.append("(o.bs_id ILIKE %s OR o.lac ILIKE %s)")
        params.extend([f"%{q}%", f"%{q}%"])

    where = " AND ".join(conditions)
    offset = (page - 1) * size

    rows = fetchall(f"""
        SELECT o.operator_code, o.operator_cn, o.lac, o.bs_id, o.tech_norm,
               o.cell_count, o.record_count, o.total_devices, o.active_days, o.independent_obs,
               o.center_lon, o.center_lat,
               ROUND(o.gps_p50_dist_m::numeric, 1) AS gps_p50_dist_m,
               ROUND(o.gps_p90_dist_m::numeric, 1) AS gps_p90_dist_m,
               ROUND(o.area_km2::numeric, 3) AS area_km2,
               ROUND(o.rsrp_avg::numeric, 1) AS rsrp_avg,
               ROUND(o.gps_original_ratio::numeric, 4) AS gps_original_ratio,
               ROUND(o.signal_original_ratio::numeric, 4) AS signal_original_ratio,
               o.collision_cell_count, o.dynamic_cell_count, o.migration_cell_count,
               o.active_cell_count, o.good_cell_count,
               o.classification, o.position_grade, o.gps_confidence, o.signal_confidence,
               o.cell_scale, o.lifecycle_state, o.anchorable,
               o.province_name, o.city_name, o.district_name,
               COALESCE(o.is_multi_centroid, false) AS is_multi_centroid
        FROM rebuild4.etl_dim_bs o
        WHERE {where}
        ORDER BY o.record_count DESC
        LIMIT %s OFFSET %s
    """, (*params, size, offset))

    total = fetchone(f"SELECT COUNT(*) as cnt FROM rebuild4.etl_dim_bs o WHERE {where}", params)

    summary = fetchone("""
        SELECT COUNT(*) as total,
               COUNT(*) FILTER (WHERE lifecycle_state = 'active') as active,
               COUNT(*) FILTER (WHERE lifecycle_state = 'observing') as observing,
               COUNT(*) FILTER (WHERE lifecycle_state = 'waiting') as waiting,
               COUNT(*) FILTER (WHERE classification = 'collision_bs') as collision,
               COUNT(*) FILTER (WHERE classification = 'dynamic_bs') as dynamic,
               COUNT(*) FILTER (WHERE classification = 'large_spread') as large_spread,
               COUNT(*) FILTER (WHERE classification = 'normal_spread') as normal,
               COUNT(*) FILTER (WHERE classification = 'multi_centroid') as multi_centroid
        FROM rebuild4.etl_dim_bs
    """)

    return envelope({
        "items": rows,
        "summary": summary or {},
        "total": total["cnt"] if total else 0,
        "page": page, "size": size,
    }, subject_scope="object", subject_note="暂无画像数据" if not rows else None, context=ctx)


# ---------------------------------------------------------------------------
# BS centroid detail (multi-centroid BS sub-clusters)
# ---------------------------------------------------------------------------
@router.get("/profiles/bs/centroids")
def profile_bs_centroids(
    operator: str = Query(...),
    lac: str = Query(...),
    bs_id: str = Query(...),
):
    rows = fetchall("""
        SELECT centroid_id, is_primary, cell_count, cell_ids,
               center_lon, center_lat,
               ROUND(area_km2::numeric, 3) AS area_km2,
               independent_obs, total_devices, active_days
        FROM rebuild4.etl_dim_bs_centroid
        WHERE operator_code = %s AND lac = %s AND bs_id = %s
        ORDER BY centroid_id
    """, (operator, lac, bs_id))
    return envelope({"centroids": rows})


# ---------------------------------------------------------------------------
# Cell  (data source: etl_dim_cell v2 — 5-step profile pipeline)
# ---------------------------------------------------------------------------
@router.get("/profiles/cell")
def profile_cell(
    q: str = Query(None),
    operator: str = Query(None),
    rat: str = Query(None),
    lac: str = Query(None),
    bs_id: str = Query(None),
    lifecycle: str = Query(None),
    drift: str = Query(None),
    grade: str = Query(None),
    scale: str = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
):
    ctx = _profile_ctx("cell", filter_operator=operator, filter_rat=rat,
                       filter_lac=lac, filter_bs=bs_id, filter_lifecycle=lifecycle,
                       filter_drift=drift, filter_grade=grade, filter_scale=scale)
    conditions = ["1=1"]
    params: list = []

    if operator:
        conditions.append("o.operator_code = %s")
        params.append(operator)
    if rat:
        conditions.append("o.tech_norm = %s")
        params.append(rat)
    if lac:
        conditions.append("o.lac = %s")
        params.append(lac)
    if bs_id:
        conditions.append("o.bs_id = %s")
        params.append(bs_id)
    if lifecycle:
        conditions.append("o.lifecycle_state = %s")
        params.append(lifecycle)
    if drift:
        conditions.append("o.drift_pattern = %s")
        params.append(drift)
    if grade:
        conditions.append("o.position_grade = %s")
        params.append(grade)
    if scale:
        conditions.append("o.cell_scale = %s")
        params.append(scale)
    if q:
        conditions.append("(o.cell_id ILIKE %s OR o.bs_id ILIKE %s OR o.lac ILIKE %s)")
        params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])

    where = " AND ".join(conditions)
    offset = (page - 1) * size

    rows = fetchall(f"""
        SELECT o.operator_code, o.operator_cn, o.lac, o.bs_id, o.cell_id,
               o.tech_norm,
               o.center_lon, o.center_lat,
               o.independent_obs, o.independent_devs, o.independent_days,
               ROUND(o.gps_original_ratio::numeric, 4) AS gps_original_ratio,
               ROUND(o.gps_valid_ratio::numeric, 4) AS gps_valid_ratio,
               ROUND(o.signal_original_ratio::numeric, 4) AS signal_original_ratio,
               ROUND(o.rsrp_avg::numeric, 1) AS rsrp_avg,
               ROUND(o.rsrq_avg::numeric, 1) AS rsrq_avg,
               ROUND(o.sinr_avg::numeric, 1) AS sinr_avg,
               ROUND(o.dist_to_bs_m::numeric, 1) AS dist_to_bs_m,
               o.active_days,
               o.lifecycle_state, o.anchorable,
               o.gps_valid_count, o.gps_original_count, o.distinct_dev_id,
               ROUND(o.p50_radius_m::numeric, 1) AS p50_radius_m,
               ROUND(o.p90_radius_m::numeric, 1) AS p90_radius_m,
               ROUND(o.observed_span_hours::numeric, 1) AS observed_span_hours,
               o.record_count,
               o.drift_pattern, ROUND(o.drift_max_spread_m::numeric, 0) AS drift_max_spread_m,
               ROUND(o.drift_net_m::numeric, 0) AS drift_net_m, o.drift_days,
               o.position_grade, o.gps_confidence, o.signal_confidence,
               o.cell_scale, o.is_collision, o.is_dynamic,
               o.province_name, o.city_name, o.district_name
        FROM rebuild4.etl_dim_cell o
        WHERE {where}
        ORDER BY o.record_count DESC
        LIMIT %s OFFSET %s
    """, (*params, size, offset))

    total = fetchone(f"SELECT COUNT(*) as cnt FROM rebuild4.etl_dim_cell o WHERE {where}", params)

    summary = fetchone("""
        SELECT COUNT(*) as total,
               COUNT(*) FILTER (WHERE lifecycle_state = 'active') as active,
               COUNT(*) FILTER (WHERE lifecycle_state = 'observing') as observing,
               COUNT(*) FILTER (WHERE lifecycle_state = 'waiting') as waiting,
               COUNT(*) FILTER (WHERE is_collision) as collision,
               COUNT(*) FILTER (WHERE is_dynamic) as dynamic,
               COUNT(*) FILTER (WHERE drift_pattern = 'migration') as migration,
               COUNT(*) FILTER (WHERE position_grade = 'excellent') as grade_excellent,
               COUNT(*) FILTER (WHERE position_grade = 'good') as grade_good,
               COUNT(*) FILTER (WHERE position_grade = 'qualified') as grade_qualified,
               COUNT(*) FILTER (WHERE position_grade = 'unqualified') as grade_unqualified,
               COUNT(*) FILTER (WHERE cell_scale = 'major') as scale_major,
               COUNT(*) FILTER (WHERE cell_scale = 'large') as scale_large,
               COUNT(*) FILTER (WHERE cell_scale = 'medium') as scale_medium,
               COUNT(*) FILTER (WHERE cell_scale = 'small') as scale_small,
               COUNT(*) FILTER (WHERE cell_scale = 'micro') as scale_micro
        FROM rebuild4.etl_dim_cell
    """)

    return envelope({
        "items": rows,
        "summary": summary or {},
        "total": total["cnt"] if total else 0,
        "page": page, "size": size,
    }, subject_scope="object", subject_note="暂无画像数据" if not rows else None, context=ctx)
