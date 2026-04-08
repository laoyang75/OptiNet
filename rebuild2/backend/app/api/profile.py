"""L4 画像基线 API：LAC / BS / Cell 画像。"""

from __future__ import annotations
from fastapi import APIRouter, Depends, Query
from typing import Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db

router = APIRouter(prefix="/profile", tags=["profile"])


# ════════════════════════════════════════════════════════════
#  LAC 画像 — 样本 LAC 列表 + 7 天汇总
# ════════════════════════════════════════════════════════════

@router.get("/lac/sample/list")
async def get_lac_sample_list(db: AsyncSession = Depends(get_db)):
    """6 个样本 LAC 的 7 天汇总概况 + 覆盖面积/密度。"""

    rows = [dict(r) for r in (await db.execute(text("""
        WITH summary AS (
            SELECT
                operator_code,
                tech_norm,
                lac,
                SUM(record_cnt)::bigint                     AS record_cnt,
                MAX(bs_cnt)::int                            AS bs_cnt,
                MAX(cell_cnt)::int                          AS cell_cnt,
                MAX(device_cnt)::int                        AS device_cnt,
                COUNT(DISTINCT report_date)::int             AS active_days,
                -- GPS 健康
                SUM(gps_original_cnt)::bigint                AS gps_original_cnt,
                SUM(gps_valid_cnt)::bigint                   AS gps_valid_cnt,
                SUM(gps_cell_center_cnt)::bigint             AS gps_cell_center_cnt,
                SUM(gps_bs_center_cnt)::bigint               AS gps_bs_center_cnt,
                SUM(gps_bs_center_risk_cnt)::bigint          AS gps_bs_center_risk_cnt,
                ROUND(SUM(gps_original_cnt)::numeric / NULLIF(SUM(record_cnt), 0), 4)  AS gps_original_ratio,
                ROUND(SUM(gps_valid_cnt)::numeric / NULLIF(SUM(record_cnt), 0), 4)     AS gps_valid_ratio,
                -- 信号健康
                SUM(signal_original_cnt)::bigint             AS signal_original_cnt,
                SUM(signal_fill_cnt)::bigint                 AS signal_fill_cnt,
                ROUND(SUM(signal_original_cnt)::numeric / NULLIF(SUM(record_cnt), 0), 4)  AS signal_original_ratio,
                ROUND(SUM(signal_valid_cnt)::numeric / NULLIF(SUM(record_cnt), 0), 4)     AS signal_valid_ratio,
                -- 信号均值
                ROUND(SUM(rsrp_sum)::numeric / NULLIF(SUM(signal_cnt), 0), 1)  AS rsrp_avg,
                ROUND(SUM(rsrq_sum)::numeric / NULLIF(SUM(signal_cnt), 0), 1)  AS rsrq_avg,
                ROUND(SUM(sinr_sum)::numeric / NULLIF(SUM(signal_cnt), 0), 1)  AS sinr_avg,
                -- 异常
                SUM(excluded_record_cnt)::bigint  AS excluded_record_cnt,
                MAX(excluded_bs_cnt)::int         AS excluded_bs_cnt,
                ROUND(SUM(excluded_record_cnt)::numeric / NULLIF(SUM(record_cnt) + SUM(excluded_record_cnt), 0), 4) AS excluded_ratio
            FROM rebuild2._sample_lac_profile_v1
            GROUP BY 1, 2, 3
        ),
        -- 覆盖面积 + GPS 中心点
        area AS (
            SELECT
                f.operator_code, f.tech_norm, f.lac,
                ROUND(AVG(f.lon_final)::numeric, 6) AS center_lon,
                ROUND(AVG(f.lat_final)::numeric, 6) AS center_lat,
                ROUND((
                    (PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY f.lon_final)
                     - PERCENTILE_CONT(0.05) WITHIN GROUP (ORDER BY f.lon_final))
                    * 111.32 * COS(RADIANS(AVG(f.lat_final)))
                    * (PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY f.lat_final)
                       - PERCENTILE_CONT(0.05) WITHIN GROUP (ORDER BY f.lat_final))
                    * 110.57
                )::numeric, 2) AS area_km2
            FROM rebuild2._sample_lac_facts f
            LEFT JOIN rebuild2._research_bs_classification_v2 ex
                ON f.operator_code = ex.operator_code
                AND f.tech_norm = ex.tech_norm
                AND f.lac = ex.lac
                AND f.bs_id = ex.bs_id
                AND ex.classification_v2 IN ('dynamic_bs','collision_confirmed','collision_suspected')
            WHERE ex.bs_id IS NULL
              AND f.lon_final IS NOT NULL AND f.lat_final IS NOT NULL
            GROUP BY 1, 2, 3
        ),
        -- 异常 BS 分类明细
        anomaly_detail AS (
            SELECT
                f.operator_code, f.tech_norm, f.lac,
                COUNT(DISTINCT f.bs_id) FILTER (WHERE c.classification_v2 = 'dynamic_bs')::int           AS dynamic_bs_cnt,
                COUNT(DISTINCT f.bs_id) FILTER (WHERE c.classification_v2 = 'collision_confirmed')::int  AS collision_confirmed_cnt,
                COUNT(DISTINCT f.bs_id) FILTER (WHERE c.classification_v2 = 'collision_suspected')::int  AS collision_suspected_cnt,
                COUNT(DISTINCT f.bs_id) FILTER (WHERE c.classification_v2 = 'single_large')::int         AS single_large_cnt,
                COUNT(DISTINCT f.bs_id) FILTER (WHERE c.classification_v2 = 'normal_spread')::int        AS normal_spread_cnt
            FROM (SELECT DISTINCT operator_code, tech_norm, lac, bs_id FROM rebuild2._sample_lac_facts) f
            LEFT JOIN rebuild2._research_bs_classification_v2 c USING (operator_code, tech_norm, lac, bs_id)
            WHERE c.classification_v2 IS NOT NULL
            GROUP BY 1, 2, 3
        )
        SELECT
            s.*,
            a.center_lon,
            a.center_lat,
            a.area_km2,
            CASE WHEN a.area_km2 > 0
                THEN ROUND(s.record_cnt::numeric / a.area_km2, 0)
                ELSE NULL END AS report_density_per_km2,
            CASE WHEN a.area_km2 > 0
                THEN ROUND(s.bs_cnt::numeric / a.area_km2, 1)
                ELSE NULL END AS bs_density_per_km2,
            COALESCE(ad.dynamic_bs_cnt, 0)           AS dynamic_bs_cnt,
            COALESCE(ad.collision_confirmed_cnt, 0)  AS collision_confirmed_cnt,
            COALESCE(ad.collision_suspected_cnt, 0)  AS collision_suspected_cnt,
            COALESCE(ad.single_large_cnt, 0)         AS single_large_cnt,
            COALESCE(ad.normal_spread_cnt, 0)        AS normal_spread_cnt,
            loc.province_name,
            loc.city_name    AS location_city,
            loc.district_name AS location_district,
            loc.district_cnt  AS location_district_cnt,
            loc.districts_list AS location_districts
        FROM summary s
        LEFT JOIN area a USING (operator_code, tech_norm, lac)
        LEFT JOIN anomaly_detail ad USING (operator_code, tech_norm, lac)
        LEFT JOIN rebuild2._sample_lac_location loc USING (operator_code, tech_norm, lac)
        ORDER BY s.operator_code, s.tech_norm, s.lac
    """))).mappings().all()]

    return {"lacs": rows}


# ════════════════════════════════════════════════════════════
#  LAC 画像 — 单个 LAC 的小时级潮汐
# ════════════════════════════════════════════════════════════

@router.get("/lac/sample/hourly")
async def get_lac_sample_hourly(
    operator_code: str = Query(...),
    tech_norm: str = Query(...),
    lac: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """单个 LAC 的 24 小时潮汐（7 天聚合）。"""

    rows = [dict(r) for r in (await db.execute(text("""
        SELECT
            hour_of_day,
            SUM(record_cnt)::bigint  AS record_cnt,
            MAX(device_cnt)::int     AS device_cnt,
            MAX(bs_cnt)::int         AS bs_cnt,
            -- GPS
            ROUND(SUM(gps_original_cnt)::numeric / NULLIF(SUM(record_cnt), 0), 4)  AS gps_original_ratio,
            ROUND(SUM(gps_valid_cnt)::numeric / NULLIF(SUM(record_cnt), 0), 4)     AS gps_valid_ratio,
            -- 信号
            ROUND(SUM(signal_original_cnt)::numeric / NULLIF(SUM(record_cnt), 0), 4)  AS signal_original_ratio,
            -- 信号均值
            ROUND(SUM(rsrp_sum)::numeric / NULLIF(SUM(signal_cnt), 0), 1)  AS rsrp_avg,
            ROUND(SUM(sinr_sum)::numeric / NULLIF(SUM(signal_cnt), 0), 1)  AS sinr_avg,
            -- 异常
            SUM(excluded_record_cnt)::bigint  AS excluded_cnt,
            MAX(excluded_bs_cnt)::int         AS excluded_bs_cnt
        FROM rebuild2._sample_lac_profile_v1
        WHERE operator_code = :op AND tech_norm = :tech AND lac = :lac
        GROUP BY 1
        ORDER BY 1
    """), {"op": operator_code, "tech": tech_norm, "lac": lac})).mappings().all()]

    return {"hourly": rows}


# ════════════════════════════════════════════════════════════
#  LAC 画像 — 单个 LAC 的日级趋势
# ════════════════════════════════════════════════════════════

@router.get("/lac/sample/daily")
async def get_lac_sample_daily(
    operator_code: str = Query(...),
    tech_norm: str = Query(...),
    lac: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """单个 LAC 的 7 天日级趋势。"""

    rows = [dict(r) for r in (await db.execute(text("""
        SELECT
            report_date::text AS report_date,
            SUM(record_cnt)::bigint  AS record_cnt,
            MAX(bs_cnt)::int         AS bs_cnt,
            MAX(cell_cnt)::int       AS cell_cnt,
            MAX(device_cnt)::int     AS device_cnt,
            ROUND(SUM(gps_original_cnt)::numeric / NULLIF(SUM(record_cnt), 0), 4)     AS gps_original_ratio,
            ROUND(SUM(signal_original_cnt)::numeric / NULLIF(SUM(record_cnt), 0), 4)  AS signal_original_ratio,
            ROUND(SUM(rsrp_sum)::numeric / NULLIF(SUM(signal_cnt), 0), 1)             AS rsrp_avg,
            SUM(excluded_record_cnt)::bigint  AS excluded_cnt
        FROM rebuild2._sample_lac_profile_v1
        WHERE operator_code = :op AND tech_norm = :tech AND lac = :lac
        GROUP BY 1
        ORDER BY 1
    """), {"op": operator_code, "tech": tech_norm, "lac": lac})).mappings().all()]

    return {"daily": rows}


# ════════════════════════════════════════════════════════════
#  BS 画像 — 样本 BS 列表（汇总表）
# ════════════════════════════════════════════════════════════

@router.get("/bs/sample/list")
async def get_bs_sample_list(
    operator_code: Optional[str] = Query(None),
    tech_norm: Optional[str] = Query(None),
    lac: Optional[str] = Query(None),
    classification: Optional[str] = Query(None),
    gps_confidence: Optional[str] = Query(None),
    sort_by: str = Query("total_records"),
    sort_dir: str = Query("desc"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """样本 BS 汇总列表，支持筛选、排序、分页。"""

    allowed_sorts = {
        "total_records", "total_devices", "total_cells", "gps_p50_dist_m",
        "gps_p90_dist_m", "area_km2", "rsrp_avg", "gps_original_ratio",
        "signal_original_ratio", "bs_id",
    }
    col = sort_by if sort_by in allowed_sorts else "total_records"
    direction = "ASC" if sort_dir.lower() == "asc" else "DESC"

    filters = []
    params: dict = {"lim": limit, "off": offset}
    if operator_code:
        filters.append("operator_code = :op")
        params["op"] = operator_code
    if tech_norm:
        filters.append("tech_norm = :tech")
        params["tech"] = tech_norm
    if lac:
        filters.append("lac = :lac")
        params["lac"] = lac
    if classification == "normal":
        filters.append("classification_v2 IS NULL")
    elif classification:
        filters.append("classification_v2 = :cls")
        params["cls"] = classification
    if gps_confidence:
        filters.append("gps_confidence = :gc")
        params["gc"] = gps_confidence

    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    rows = [dict(r) for r in (await db.execute(text(f"""
        SELECT *
        FROM rebuild2._sample_bs_profile_summary
        {where}
        ORDER BY {col} {direction} NULLS LAST
        LIMIT :lim OFFSET :off
    """), params)).mappings().all()]

    total = (await db.execute(text(f"""
        SELECT COUNT(*)::int AS cnt FROM rebuild2._sample_bs_profile_summary {where}
    """), params)).scalar()

    # 汇总统计
    stats = dict((await db.execute(text(f"""
        SELECT
            COUNT(*)::int                                            AS total_bs,
            SUM(total_records)::bigint                               AS total_records,
            COUNT(*) FILTER (WHERE classification_v2 IS NOT NULL)::int AS anomaly_bs,
            COUNT(*) FILTER (WHERE gps_confidence = 'high')::int     AS gps_high,
            COUNT(*) FILTER (WHERE gps_confidence = 'medium')::int   AS gps_medium,
            COUNT(*) FILTER (WHERE gps_confidence = 'low')::int      AS gps_low,
            COUNT(*) FILTER (WHERE gps_confidence = 'none')::int     AS gps_none,
            COUNT(*) FILTER (WHERE signal_confidence = 'high')::int  AS sig_high,
            COUNT(*) FILTER (WHERE signal_confidence = 'medium')::int AS sig_medium,
            COUNT(*) FILTER (WHERE signal_confidence = 'low')::int   AS sig_low,
            -- 异常分类明细
            COUNT(*) FILTER (WHERE classification_v2 = 'dynamic_bs')::int           AS dynamic_bs_cnt,
            COUNT(*) FILTER (WHERE classification_v2 = 'collision_confirmed')::int  AS collision_confirmed_cnt,
            COUNT(*) FILTER (WHERE classification_v2 = 'collision_suspected')::int  AS collision_suspected_cnt,
            COUNT(*) FILTER (WHERE classification_v2 = 'single_large')::int         AS single_large_cnt,
            COUNT(*) FILTER (WHERE classification_v2 = 'normal_spread')::int        AS normal_spread_cnt
        FROM rebuild2._sample_bs_profile_summary
    """))).mappings().one())

    # 筛选选项
    filter_options = {}
    filter_options["lacs"] = [dict(r) for r in (await db.execute(text("""
        SELECT DISTINCT operator_code, tech_norm, lac
        FROM rebuild2._sample_bs_profile_summary
        ORDER BY 1,2,3
    """))).mappings().all()]

    return {"rows": rows, "total": total, "stats": stats, "filter_options": filter_options}


# ════════════════════════════════════════════════════════════
#  BS 画像 — 单个 BS 的小时级潮汐
# ════════════════════════════════════════════════════════════

@router.get("/bs/sample/hourly")
async def get_bs_sample_hourly(
    operator_code: str = Query(...),
    tech_norm: str = Query(...),
    lac: str = Query(...),
    bs_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """单个 BS 的 24 小时潮汐（7 天聚合）。"""

    rows = [dict(r) for r in (await db.execute(text("""
        SELECT
            hour_of_day,
            SUM(record_cnt)::bigint  AS record_cnt,
            MAX(device_cnt)::int     AS device_cnt,
            MAX(cell_cnt)::int       AS cell_cnt,
            -- GPS
            ROUND(SUM(gps_original_cnt)::numeric / NULLIF(SUM(record_cnt), 0), 4)  AS gps_original_ratio,
            ROUND(SUM(gps_valid_cnt)::numeric / NULLIF(SUM(record_cnt), 0), 4)     AS gps_valid_ratio,
            -- 信号
            ROUND(SUM(signal_original_cnt)::numeric / NULLIF(SUM(record_cnt), 0), 4)  AS signal_original_ratio,
            -- 信号均值
            ROUND(SUM(rsrp_sum)::numeric / NULLIF(SUM(signal_cnt), 0), 1)  AS rsrp_avg,
            ROUND(SUM(sinr_sum)::numeric / NULLIF(SUM(signal_cnt), 0), 1)  AS sinr_avg
        FROM rebuild2._sample_bs_profile_hourly
        WHERE operator_code = :op AND tech_norm = :tech AND lac = :lac AND bs_id = :bs
        GROUP BY 1
        ORDER BY 1
    """), {"op": operator_code, "tech": tech_norm, "lac": lac, "bs": bs_id})).mappings().all()]

    return {"hourly": rows}


# ════════════════════════════════════════════════════════════
#  BS 画像 — 单个 BS 的日级趋势
# ════════════════════════════════════════════════════════════

@router.get("/bs/sample/daily")
async def get_bs_sample_daily(
    operator_code: str = Query(...),
    tech_norm: str = Query(...),
    lac: str = Query(...),
    bs_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """单个 BS 的 7 天日级趋势。"""

    rows = [dict(r) for r in (await db.execute(text("""
        SELECT
            report_date::text AS report_date,
            SUM(record_cnt)::bigint  AS record_cnt,
            MAX(cell_cnt)::int       AS cell_cnt,
            MAX(device_cnt)::int     AS device_cnt,
            ROUND(SUM(gps_original_cnt)::numeric / NULLIF(SUM(record_cnt), 0), 4)     AS gps_original_ratio,
            ROUND(SUM(signal_original_cnt)::numeric / NULLIF(SUM(record_cnt), 0), 4)  AS signal_original_ratio,
            ROUND(SUM(rsrp_sum)::numeric / NULLIF(SUM(signal_cnt), 0), 1)             AS rsrp_avg
        FROM rebuild2._sample_bs_profile_hourly
        WHERE operator_code = :op AND tech_norm = :tech AND lac = :lac AND bs_id = :bs
        GROUP BY 1
        ORDER BY 1
    """), {"op": operator_code, "tech": tech_norm, "lac": lac, "bs": bs_id})).mappings().all()]

    return {"daily": rows}


# ════════════════════════════════════════════════════════════
#  Cell 画像 — 样本 Cell 列表（汇总表）
# ════════════════════════════════════════════════════════════

@router.get("/cell/sample/list")
async def get_cell_sample_list(
    operator_code: Optional[str] = Query(None),
    tech_norm: Optional[str] = Query(None),
    lac: Optional[str] = Query(None),
    bs_id: Optional[int] = Query(None),
    bs_classification: Optional[str] = Query(None),
    gps_confidence: Optional[str] = Query(None),
    is_dynamic: Optional[bool] = Query(None),
    sort_by: str = Query("total_records"),
    sort_dir: str = Query("desc"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """样本 Cell 汇总列表，支持筛选、排序、分页。"""

    allowed_sorts = {
        "total_records", "total_devices", "gps_p50_dist_m",
        "gps_p90_dist_m", "rsrp_avg", "gps_original_ratio",
        "signal_original_ratio", "cell_id", "bs_id", "centroid_span_m",
    }
    col = sort_by if sort_by in allowed_sorts else "total_records"
    direction = "ASC" if sort_dir.lower() == "asc" else "DESC"

    filters = []
    params: dict = {"lim": limit, "off": offset}
    if operator_code:
        filters.append("operator_code = :op")
        params["op"] = operator_code
    if tech_norm:
        filters.append("tech_norm = :tech")
        params["tech"] = tech_norm
    if lac:
        filters.append("lac = :lac")
        params["lac"] = lac
    if bs_id is not None:
        filters.append("bs_id = :bs")
        params["bs"] = bs_id
    if bs_classification == "normal":
        filters.append("bs_classification IS NULL")
    elif bs_classification:
        filters.append("bs_classification = :cls")
        params["cls"] = bs_classification
    if gps_confidence:
        filters.append("gps_confidence = :gc")
        params["gc"] = gps_confidence
    if is_dynamic is not None:
        filters.append("is_dynamic_cell = :dyn")
        params["dyn"] = is_dynamic

    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    rows = [dict(r) for r in (await db.execute(text(f"""
        SELECT *
        FROM rebuild2._sample_cell_profile_summary
        {where}
        ORDER BY {col} {direction} NULLS LAST
        LIMIT :lim OFFSET :off
    """), params)).mappings().all()]

    total = (await db.execute(text(f"""
        SELECT COUNT(*)::int AS cnt FROM rebuild2._sample_cell_profile_summary {where}
    """), params)).scalar()

    stats = dict((await db.execute(text("""
        SELECT
            COUNT(*)::int                                                AS total_cells,
            SUM(total_records)::bigint                                   AS total_records,
            COUNT(DISTINCT bs_id)::int                                   AS total_bs,
            COUNT(*) FILTER (WHERE bs_classification IS NOT NULL)::int    AS anomaly_bs_cells,
            COUNT(*) FILTER (WHERE is_dynamic_cell)::int                 AS dynamic_cells,
            COUNT(*) FILTER (WHERE gps_confidence = 'high')::int         AS gps_high,
            COUNT(*) FILTER (WHERE gps_confidence = 'medium')::int       AS gps_medium,
            COUNT(*) FILTER (WHERE gps_confidence = 'low')::int          AS gps_low,
            COUNT(*) FILTER (WHERE gps_confidence = 'none')::int         AS gps_none,
            COUNT(*) FILTER (WHERE signal_confidence = 'high')::int      AS sig_high,
            COUNT(*) FILTER (WHERE signal_confidence = 'medium')::int    AS sig_medium,
            COUNT(*) FILTER (WHERE signal_confidence = 'low')::int       AS sig_low,
            COUNT(*) FILTER (WHERE bs_classification = 'dynamic_bs')::int           AS dynamic_bs_cells,
            COUNT(*) FILTER (WHERE bs_classification = 'collision_confirmed')::int  AS collision_confirmed_cells,
            COUNT(*) FILTER (WHERE bs_classification = 'collision_suspected')::int  AS collision_suspected_cells,
            COUNT(*) FILTER (WHERE bs_classification = 'single_large')::int         AS single_large_cells,
            COUNT(*) FILTER (WHERE bs_classification = 'normal_spread')::int        AS normal_spread_cells
        FROM rebuild2._sample_cell_profile_summary
    """))).mappings().one())

    return {"rows": rows, "total": total, "stats": stats}


# ════════════════════════════════════════════════════════════
#  Cell 画像 — 单个 Cell 的小时级潮汐
# ════════════════════════════════════════════════════════════

@router.get("/cell/sample/hourly")
async def get_cell_sample_hourly(
    operator_code: str = Query(...),
    tech_norm: str = Query(...),
    lac: str = Query(...),
    bs_id: int = Query(...),
    cell_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
):
    rows = [dict(r) for r in (await db.execute(text("""
        SELECT
            hour_of_day,
            SUM(record_cnt)::bigint  AS record_cnt,
            MAX(device_cnt)::int     AS device_cnt,
            ROUND(SUM(gps_original_cnt)::numeric / NULLIF(SUM(record_cnt), 0), 4)  AS gps_original_ratio,
            ROUND(SUM(gps_valid_cnt)::numeric / NULLIF(SUM(record_cnt), 0), 4)     AS gps_valid_ratio,
            ROUND(SUM(signal_original_cnt)::numeric / NULLIF(SUM(record_cnt), 0), 4) AS signal_original_ratio,
            ROUND(SUM(rsrp_sum)::numeric / NULLIF(SUM(signal_cnt), 0), 1) AS rsrp_avg,
            ROUND(SUM(sinr_sum)::numeric / NULLIF(SUM(signal_cnt), 0), 1) AS sinr_avg
        FROM rebuild2._sample_cell_profile_hourly
        WHERE operator_code = :op AND tech_norm = :tech AND lac = :lac
          AND bs_id = :bs AND cell_id = :cell
        GROUP BY 1
        ORDER BY 1
    """), {"op": operator_code, "tech": tech_norm, "lac": lac, "bs": bs_id, "cell": cell_id})).mappings().all()]

    return {"hourly": rows}


# ════════════════════════════════════════════════════════════
#  Cell 画像 — 单个 Cell 的日级趋势
# ════════════════════════════════════════════════════════════

@router.get("/cell/sample/daily")
async def get_cell_sample_daily(
    operator_code: str = Query(...),
    tech_norm: str = Query(...),
    lac: str = Query(...),
    bs_id: int = Query(...),
    cell_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
):
    rows = [dict(r) for r in (await db.execute(text("""
        SELECT
            report_date::text AS report_date,
            SUM(record_cnt)::bigint  AS record_cnt,
            MAX(device_cnt)::int     AS device_cnt,
            ROUND(SUM(gps_original_cnt)::numeric / NULLIF(SUM(record_cnt), 0), 4)     AS gps_original_ratio,
            ROUND(SUM(signal_original_cnt)::numeric / NULLIF(SUM(record_cnt), 0), 4)  AS signal_original_ratio,
            ROUND(SUM(rsrp_sum)::numeric / NULLIF(SUM(signal_cnt), 0), 1)             AS rsrp_avg
        FROM rebuild2._sample_cell_profile_hourly
        WHERE operator_code = :op AND tech_norm = :tech AND lac = :lac
          AND bs_id = :bs AND cell_id = :cell
        GROUP BY 1
        ORDER BY 1
    """), {"op": operator_code, "tech": tech_norm, "lac": lac, "bs": bs_id, "cell": cell_id})).mappings().all()]

    return {"daily": rows}
