"""L3 问题数据研究 API：GPS 异常分析与质量评估。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

router = APIRouter(prefix="/anomaly", tags=["anomaly"])


@router.get("/overview")
async def get_overview(db: AsyncSession = Depends(get_db)):
    """研究三：GPS 样本分档 + 单设备 + GPS 补齐来源总览。"""

    # ── BS 级 GPS 分档 ──
    bs_tiers = (await db.execute(text("""
        SELECT
            CASE
                WHEN total_gps_points = 0 THEN 'no_gps'
                WHEN total_gps_points BETWEEN 1 AND 3 THEN 'low'
                WHEN total_gps_points BETWEEN 4 AND 9 THEN 'medium'
                WHEN total_gps_points >= 10 THEN 'high'
            END AS tier,
            count(*)::int AS bs_count,
            coalesce(sum(record_count), 0)::bigint AS record_count,
            count(*) FILTER (WHERE distinct_gps_devices = 1 AND total_gps_points > 0)::int AS single_device_count,
            count(*) FILTER (WHERE distinct_gps_devices <= 2 AND total_gps_points > 3)::int AS le2_device_count
        FROM rebuild2.dim_bs_refined
        GROUP BY 1
        ORDER BY 1
    """))).mappings().all()

    # ── Cell 级 GPS 分档 ──
    cell_tiers = (await db.execute(text("""
        SELECT
            CASE
                WHEN coalesce(gps_count, 0) = 0 THEN 'no_gps'
                WHEN gps_count BETWEEN 1 AND 3 THEN 'low'
                WHEN gps_count BETWEEN 4 AND 9 THEN 'medium'
                WHEN gps_count >= 10 THEN 'high'
            END AS tier,
            count(*)::int AS cell_count,
            coalesce(sum(record_count), 0)::bigint AS record_count
        FROM rebuild2.dim_cell_refined
        GROUP BY 1
        ORDER BY 1
    """))).mappings().all()

    # ── GPS 补齐来源分布 ──
    gps_source = (await db.execute(text("""
        SELECT gps_source, count(*)::bigint AS cnt
        FROM rebuild2.dwd_fact_enriched
        GROUP BY gps_source
        ORDER BY cnt DESC
    """))).mappings().all()

    # ── 单设备 BS 详情（GPS >= 4 但只有 1 台设备）──
    single_dev_detail = (await db.execute(text("""
        SELECT
            CASE
                WHEN total_gps_points BETWEEN 4 AND 9 THEN 'medium'
                WHEN total_gps_points >= 10 THEN 'high'
            END AS gps_tier,
            count(*)::int AS bs_count,
            coalesce(sum(record_count), 0)::bigint AS record_count,
            round(avg(gps_p90_dist_m))::int AS avg_p90_dist,
            round(avg(gps_max_dist_m))::int AS avg_max_dist
        FROM rebuild2.dim_bs_refined
        WHERE distinct_gps_devices = 1 AND total_gps_points >= 4
        GROUP BY 1
        ORDER BY 1
    """))).mappings().all()

    # ── 总数统计 ──
    totals = (await db.execute(text("""
        SELECT
            count(*)::int AS total_bs,
            count(*) FILTER (WHERE total_gps_points = 0)::int AS bs_no_gps,
            count(*) FILTER (WHERE total_gps_points BETWEEN 1 AND 3)::int AS bs_low_gps,
            count(*) FILTER (WHERE distinct_gps_devices = 1 AND total_gps_points >= 4)::int AS bs_single_device,
            count(*) FILTER (WHERE total_gps_points >= 10 AND (gps_p90_dist_m > 1500 OR gps_max_dist_m > 5000))::int AS bs_high_spread
        FROM rebuild2.dim_bs_refined
    """))).mappings().one()

    cell_totals = (await db.execute(text("""
        SELECT
            count(*)::int AS total_cell,
            count(*) FILTER (WHERE coalesce(gps_count, 0) = 0)::int AS cell_no_gps,
            count(*) FILTER (WHERE gps_count BETWEEN 1 AND 3)::int AS cell_low_gps,
            count(*) FILTER (WHERE gps_anomaly = true)::int AS cell_gps_anomaly
        FROM rebuild2.dim_cell_refined
    """))).mappings().one()

    return {
        "bs_tiers": [dict(r) for r in bs_tiers],
        "cell_tiers": [dict(r) for r in cell_tiers],
        "gps_source": [dict(r) for r in gps_source],
        "single_dev_detail": [dict(r) for r in single_dev_detail],
        "bs_totals": dict(totals),
        "cell_totals": dict(cell_totals),
    }


@router.get("/centroid")
async def get_centroid_analysis(db: AsyncSession = Depends(get_db)):
    """质心分析：漏斗 + 各分类详情。"""

    # ── 漏斗数据 ──
    funnel = {}

    # 全量
    funnel["total"] = dict((await db.execute(text("""
        SELECT count(*)::int AS bs, coalesce(sum(record_count),0)::bigint AS records
        FROM rebuild2.dim_bs_refined
    """))).mappings().one())

    # 数据不足
    funnel["insufficient"] = dict((await db.execute(text("""
        SELECT count(*)::int AS bs, coalesce(sum(record_count),0)::bigint AS records
        FROM rebuild2.dim_bs_refined
        WHERE total_gps_points <= 3
           OR (distinct_gps_devices = 1 AND total_gps_points >= 4)
    """))).mappings().one())

    # 正常 BS
    funnel["normal"] = dict((await db.execute(text("""
        SELECT count(*)::int AS bs, coalesce(sum(record_count),0)::bigint AS records
        FROM rebuild2.dim_bs_refined
        WHERE total_gps_points >= 4
          AND NOT (distinct_gps_devices = 1 AND total_gps_points >= 4)
          AND NOT (
              total_gps_points >= 10 AND distinct_gps_devices >= 2 AND (
                  gps_p90_dist_m > 1500 OR gps_max_dist_m > 5000
                  OR (had_outlier_removal = true AND gps_p90_dist_m > 1000)
              )
          )
    """))).mappings().one())

    # 异常候选细分：基于 Cell 质心法 v2
    funnel["candidates"] = [dict(r) for r in (await db.execute(text("""
        SELECT
            classification_v2 AS category,
            count(*)::int AS bs,
            coalesce(sum(record_count),0)::bigint AS records,
            round(avg(distinct_gps_devices))::int AS avg_devices,
            round(avg(static_cell_span_m))::int AS avg_cell_span
        FROM rebuild2._research_bs_classification_v2
        GROUP BY 1
        ORDER BY 2 DESC
    """))).mappings().all()]

    # ── 确认碰撞 TOP 50 ──
    collision = [dict(r) for r in (await db.execute(text("""
        SELECT
            operator_code, tech_norm, lac, bs_id,
            record_count::bigint, distinct_gps_devices, total_gps_points,
            round(gps_p90_dist_m)::int AS p90_dist,
            static_cell_span_m AS cell_span,
            static_cells, dynamic_cells, total_cells,
            round(device_cross_rate * 100, 1) AS cross_pct
        FROM rebuild2._research_bs_classification_v2
        WHERE classification_v2 = 'collision_confirmed'
        ORDER BY record_count DESC
        LIMIT 50
    """))).mappings().all()]

    # ── 疑似碰撞 TOP 50 ──
    suspected = [dict(r) for r in (await db.execute(text("""
        SELECT
            operator_code, tech_norm, lac, bs_id,
            record_count::bigint, distinct_gps_devices, total_gps_points,
            round(gps_p90_dist_m)::int AS p90_dist,
            static_cell_span_m AS cell_span,
            static_cells, dynamic_cells,
            round(device_cross_rate * 100, 1) AS cross_pct
        FROM rebuild2._research_bs_classification_v2
        WHERE classification_v2 = 'collision_suspected'
        ORDER BY record_count DESC
        LIMIT 50
    """))).mappings().all()]

    # ── 面积大 TOP 50 ──
    large_area = [dict(r) for r in (await db.execute(text("""
        SELECT
            operator_code, tech_norm, lac, bs_id,
            record_count::bigint, distinct_gps_devices, total_gps_points,
            round(gps_p90_dist_m)::int AS p90_dist,
            static_cell_span_m AS cell_span,
            static_cells, dynamic_cells
        FROM rebuild2._research_bs_classification_v2
        WHERE classification_v2 = 'single_large'
        ORDER BY record_count DESC
        LIMIT 50
    """))).mappings().all()]

    return {
        "funnel": funnel,
        "collision": collision,
        "suspected": suspected,
        "large_area": large_area,
    }
