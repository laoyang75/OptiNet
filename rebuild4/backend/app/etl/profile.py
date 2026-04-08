"""画像构建管道: etl_filled → etl_dim_cell / etl_dim_bs / etl_dim_lac。

5 步 Cell 画像 + BS/LAC 级联，SQL 驱动，Python 编排。
算法规格来自 docs/02_profile/00_总览.md、01_cell.md、04_cell_research.md。
"""
from dataclasses import dataclass, field
from pathlib import Path
import yaml
from ..core.database import execute, fetchone, fetchall

_DEFAULT_PARAMS_PATH = Path(__file__).parent / "profile_params.yaml"


def _load_params(params_path: str = None) -> dict:
    """加载业务阈值参数。"""
    p = Path(params_path) if params_path else _DEFAULT_PARAMS_PATH
    with open(p) as f:
        return yaml.safe_load(f)


@dataclass
class ProfileStepResult:
    step: str
    output_count: int = 0
    details: dict = field(default_factory=dict)


@dataclass
class ProfileResult:
    steps: list = field(default_factory=list)
    cell_count: int = 0
    bs_count: int = 0
    lac_count: int = 0

    @property
    def summary(self):
        return {s.step: {"out": s.output_count, **s.details} for s in self.steps}


# ============================================================
# 入口
# ============================================================

def run_profile(params_path: str = None) -> ProfileResult:
    """运行完整画像管道：独立观测 → 质心/半径 → 漂移 → Cell → BS → LAC。"""
    params = _load_params(params_path)
    result = ProfileResult()

    r1 = _step1_independent_obs(end_date=None)
    result.steps.append(r1)

    r2 = _step2_cell_centroid_radius(end_date=None)
    result.steps.append(r2)

    r3 = _step3_drift_analysis(params)
    result.steps.append(r3)

    r4 = _step4_build_cell(params)
    result.steps.append(r4)
    result.cell_count = r4.output_count

    r5 = _step5_build_bs(params)
    result.steps.append(r5)
    result.bs_count = r5.output_count

    r6 = _step6_build_lac(params)
    result.steps.append(r6)
    result.lac_count = r6.output_count

    _cleanup_intermediates()

    return result


# ============================================================
# Step 1: 独立观测点 (cell_id, minute) 去重
# ============================================================

def _step1_independent_obs(end_date: str = None) -> ProfileStepResult:
    """从 etl_filled 构建分钟级独立观测点表。"""
    date_filter = f"WHERE DATE(ts_std) <= '{end_date}'" if end_date else ""
    execute("DROP TABLE IF EXISTS rebuild4._pf_obs")
    execute(f"""
        CREATE TABLE rebuild4._pf_obs AS
        SELECT
            operator_code, operator_cn, lac::text AS lac,
            bs_id::text AS bs_id, cell_id::text AS cell_id, tech_norm,
            date_trunc('minute', ts_std) AS obs_minute,
            DATE(ts_std)                 AS obs_date,
            -- GPS: 仅用原始有效值 (中国边界)
            AVG(CASE WHEN lon_raw BETWEEN 73 AND 135
                      AND lat_raw BETWEEN 3 AND 54
                     THEN lon_raw END) AS lon,
            AVG(CASE WHEN lon_raw BETWEEN 73 AND 135
                      AND lat_raw BETWEEN 3 AND 54
                     THEN lat_raw END) AS lat,
            -- 信号: 仅合理范围
            AVG(CASE WHEN rsrp BETWEEN -156 AND 0 THEN rsrp END) AS rsrp,
            AVG(CASE WHEN rsrq BETWEEN -50  AND 0 THEN rsrq END) AS rsrq,
            AVG(CASE WHEN sinr BETWEEN -30  AND 50 THEN sinr END) AS sinr,
            COUNT(DISTINCT dev_id) AS dev_count,
            COUNT(*)               AS raw_records,
            -- 来源标记
            COUNT(CASE WHEN gps_fill_source = 'raw_gps' THEN 1 END) AS gps_original_records,
            COUNT(CASE WHEN rsrp IS NOT NULL THEN 1 END)            AS signal_original_records
        FROM rebuild4.etl_filled
        {date_filter}
        GROUP BY operator_code, operator_cn, lac, bs_id, cell_id, tech_norm,
                 date_trunc('minute', ts_std), DATE(ts_std)
    """)
    row = fetchone("SELECT COUNT(*) AS cnt FROM rebuild4._pf_obs")
    return ProfileStepResult(step="independent_obs", output_count=row["cnt"])


# ============================================================
# Step 2: Cell 质心 + P50/P90 半径
# ============================================================

def _step2_cell_centroid_radius(end_date: str = None) -> ProfileStepResult:
    """计算每个 Cell 的中位数质心和 P50/P90 半径。"""

    # 2a: 质心 + 基础统计
    execute("DROP TABLE IF EXISTS rebuild4._pf_cell_centroid")
    execute("""
        CREATE TABLE rebuild4._pf_cell_centroid AS
        SELECT
            cell_id,
            MODE() WITHIN GROUP (ORDER BY operator_code)  AS operator_code,
            MODE() WITHIN GROUP (ORDER BY operator_cn)    AS operator_cn,
            MODE() WITHIN GROUP (ORDER BY lac)            AS lac,
            MODE() WITHIN GROUP (ORDER BY bs_id)          AS bs_id,
            MODE() WITHIN GROUP (ORDER BY tech_norm)      AS tech_norm,
            -- 独立观测统计
            COUNT(*)                        AS independent_obs,
            COUNT(DISTINCT obs_date)        AS independent_days,
            -- GPS 有效观测数
            COUNT(lon)                      AS gps_valid_count,
            -- 中位数质心
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lon) AS center_lon,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lat) AS center_lat,
            -- 信号均值
            AVG(rsrp) AS rsrp_avg,
            AVG(rsrq) AS rsrq_avg,
            AVG(sinr) AS sinr_avg,
            -- 时间跨度
            EXTRACT(EPOCH FROM MAX(obs_minute) - MIN(obs_minute)) / 3600.0
                AS observed_span_hours,
            -- 原始记录统计 (从 obs 汇总)
            SUM(raw_records)              AS record_count,
            SUM(gps_original_records)     AS gps_original_count,
            SUM(signal_original_records)  AS signal_original_count
        FROM rebuild4._pf_obs
        GROUP BY cell_id
    """)

    # 2b: 独立设备数 (需要从原始数据计算，minute 级去重不够)
    date_filter = f"WHERE DATE(ts_std) <= '{end_date}'" if end_date else ""
    execute("DROP TABLE IF EXISTS rebuild4._pf_cell_devs")
    execute(f"""
        CREATE TABLE rebuild4._pf_cell_devs AS
        SELECT cell_id::text AS cell_id, COUNT(DISTINCT dev_id) AS distinct_dev_id
        FROM rebuild4.etl_filled
        {date_filter}
        GROUP BY cell_id
    """)

    # 2c: P50/P90 半径 (距质心距离的百分位)
    execute("DROP TABLE IF EXISTS rebuild4._pf_cell_radius")
    execute("""
        CREATE TABLE rebuild4._pf_cell_radius AS
        SELECT
            o.cell_id,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY
                SQRT(POWER((o.lon - c.center_lon) * 85300, 2)
                   + POWER((o.lat - c.center_lat) * 111000, 2))
            ) AS p50_radius_m,
            PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY
                SQRT(POWER((o.lon - c.center_lon) * 85300, 2)
                   + POWER((o.lat - c.center_lat) * 111000, 2))
            ) AS p90_radius_m
        FROM rebuild4._pf_obs o
        JOIN rebuild4._pf_cell_centroid c ON o.cell_id = c.cell_id
        WHERE o.lon IS NOT NULL
        GROUP BY o.cell_id
    """)

    # 2d: Cell → BS 距离 (BS 质心 = 其下所有 Cell 质心的中位数)
    execute("DROP TABLE IF EXISTS rebuild4._pf_bs_center")
    execute("""
        CREATE TABLE rebuild4._pf_bs_center AS
        SELECT
            bs_id,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY center_lon) AS bs_lon,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY center_lat) AS bs_lat
        FROM rebuild4._pf_cell_centroid
        WHERE center_lon IS NOT NULL
        GROUP BY bs_id
    """)

    row = fetchone("SELECT COUNT(*) AS cnt FROM rebuild4._pf_cell_centroid")
    return ProfileStepResult(step="cell_centroid_radius", output_count=row["cnt"])


# ============================================================
# Step 3: 漂移分析 (日质心)
# ============================================================

def _step3_drift_analysis(params: dict = None) -> ProfileStepResult:
    """基于每日质心的漂移检测和分类。"""
    if params is None:
        params = _load_params()
    dr = params["drift"]

    # 3a: 每日质心
    execute("DROP TABLE IF EXISTS rebuild4._pf_daily_centroid")
    execute("""
        CREATE TABLE rebuild4._pf_daily_centroid AS
        SELECT
            cell_id, obs_date,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lon) AS day_lon,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lat) AS day_lat,
            COUNT(DISTINCT dev_count) AS day_devs
        FROM rebuild4._pf_obs
        WHERE lon IS NOT NULL
        GROUP BY cell_id, obs_date
    """)

    # 3b: 漂移指标 (max_spread, net_drift, ratio)
    execute("DROP TABLE IF EXISTS rebuild4._pf_cell_drift")
    execute(f"""
        CREATE TABLE rebuild4._pf_cell_drift AS
        WITH pairs AS (
            SELECT
                a.cell_id,
                SQRT(POWER((a.day_lon - b.day_lon) * 85300, 2)
                   + POWER((a.day_lat - b.day_lat) * 111000, 2)) AS pair_dist_m
            FROM rebuild4._pf_daily_centroid a
            JOIN rebuild4._pf_daily_centroid b
              ON a.cell_id = b.cell_id AND a.obs_date < b.obs_date
        ),
        spread AS (
            SELECT cell_id, MAX(pair_dist_m) AS max_spread_m
            FROM pairs GROUP BY cell_id
        ),
        endpoints AS (
            SELECT DISTINCT ON (cell_id)
                d.cell_id,
                SQRT(POWER((d.day_lon - f.day_lon) * 85300, 2)
                   + POWER((d.day_lat - f.day_lat) * 111000, 2)) AS net_drift_m,
                (SELECT COUNT(DISTINCT obs_date) FROM rebuild4._pf_daily_centroid
                 WHERE cell_id = d.cell_id) AS drift_days
            FROM rebuild4._pf_daily_centroid d
            JOIN (
                SELECT DISTINCT ON (cell_id) cell_id, day_lon, day_lat
                FROM rebuild4._pf_daily_centroid ORDER BY cell_id, obs_date
            ) f ON d.cell_id = f.cell_id
            ORDER BY d.cell_id, d.obs_date DESC
        )
        SELECT
            e.cell_id,
            COALESCE(s.max_spread_m, 0) AS drift_max_spread_m,
            e.net_drift_m               AS drift_net_m,
            e.drift_days,
            -- 漂移分类
            CASE
                WHEN e.drift_days < {dr['min_days']} THEN 'insufficient'
                WHEN s.max_spread_m >= {dr['collision_min_spread_m']}
                 AND e.net_drift_m / NULLIF(s.max_spread_m, 0) < {dr['collision_max_ratio']}
                    THEN 'collision'
                WHEN s.max_spread_m < {dr['stable_max_spread_m']} THEN 'stable'
                WHEN s.max_spread_m >= {dr['collision_min_spread_m']}
                 AND e.net_drift_m / NULLIF(s.max_spread_m, 0) >= {dr['migration_min_ratio']}
                    THEN 'migration'
                WHEN s.max_spread_m BETWEEN {dr['stable_max_spread_m']} AND {dr['large_coverage_max_spread_m']}
                 AND e.net_drift_m / NULLIF(s.max_spread_m, 0) >= {dr['migration_min_ratio']}
                    THEN 'large_coverage'
                ELSE 'moderate_drift'
            END AS drift_pattern
        FROM endpoints e
        LEFT JOIN spread s ON e.cell_id = s.cell_id
    """)

    row = fetchone("""
        SELECT COUNT(*) AS cnt,
               COUNT(*) FILTER (WHERE drift_pattern = 'collision') AS collision
        FROM rebuild4._pf_cell_drift
    """)
    return ProfileStepResult(
        step="drift_analysis", output_count=row["cnt"],
        details={"collision": row["collision"]},
    )


# ============================================================
# Step 4: 组装最终 Cell 画像
# ============================================================

def _step4_build_cell(params: dict = None) -> ProfileStepResult:
    """组装 etl_dim_cell：合并质心、半径、漂移、分级、生命周期。"""
    if params is None:
        params = _load_params()
    pg = params["position_grade"]
    gc = params["gps_confidence"]
    sc = params["signal_confidence"]
    cs = params["cell_scale"]
    lc = params["lifecycle"]
    anc = params["anchorable"]
    dyn = params["is_dynamic"]
    execute("DROP TABLE IF EXISTS rebuild4.etl_dim_cell")
    execute(f"""
        CREATE TABLE rebuild4.etl_dim_cell AS
        SELECT
            c.operator_code, c.operator_cn, c.lac,
            c.bs_id, c.cell_id, c.tech_norm,

            -- 记录统计
            c.record_count,
            c.gps_valid_count,
            c.gps_original_count,
            d.distinct_dev_id,
            c.observed_span_hours,
            c.independent_days  AS active_days,
            c.independent_obs,
            -- 独立设备 = 去重设备数, 独立天数
            d.distinct_dev_id   AS independent_devs,
            c.independent_days,

            -- 空间
            c.center_lon, c.center_lat,
            r.p50_radius_m, r.p90_radius_m,
            -- Cell→BS 距离
            CASE WHEN c.center_lon IS NOT NULL AND bc.bs_lon IS NOT NULL THEN
                SQRT(POWER((c.center_lon - bc.bs_lon) * 85300, 2)
                   + POWER((c.center_lat - bc.bs_lat) * 111000, 2))
            END AS dist_to_bs_m,

            -- 信号
            c.rsrp_avg, c.rsrq_avg, c.sinr_avg,

            -- 数据质量比率
            CASE WHEN c.record_count > 0
                 THEN c.gps_original_count::float / c.record_count END
                AS gps_original_ratio,
            CASE WHEN c.independent_obs > 0
                 THEN c.gps_valid_count::float / c.independent_obs END
                AS gps_valid_ratio,
            CASE WHEN c.record_count > 0
                 THEN c.signal_original_count::float / c.record_count END
                AS signal_original_ratio,
            -- signal_valid_ratio: 信号有效的比率 (有 rsrp 的观测 / 总观测)
            CASE WHEN c.independent_obs > 0
                 THEN c.gps_valid_count::float / c.independent_obs END
                AS signal_valid_ratio,

            -- 漂移
            dr.drift_pattern,
            dr.drift_max_spread_m,
            dr.drift_net_m,
            dr.drift_days,

            -- 质量分级 (position_grade)
            CASE
                WHEN c.gps_valid_count = 0 THEN 'unqualified'
                WHEN c.independent_obs >= {pg['excellent']['min_obs']} AND d.distinct_dev_id >= {pg['excellent']['min_devs']}
                 AND COALESCE(r.p90_radius_m, 99999) < {pg['excellent']['max_p90_m']} THEN 'excellent'
                WHEN c.independent_obs >= {pg['good']['min_obs']} AND d.distinct_dev_id >= {pg['good']['min_devs']}
                    THEN 'good'
                WHEN c.independent_obs >= {pg['qualified']['min_obs']} THEN 'qualified'
                ELSE 'unqualified'
            END AS position_grade,

            -- GPS 置信度
            CASE
                WHEN c.gps_valid_count >= {gc['high']['min_gps_valid']} AND d.distinct_dev_id >= {gc['high']['min_devs']} THEN 'high'
                WHEN c.gps_valid_count >= {gc['medium']['min_gps_valid']} AND d.distinct_dev_id >= {gc['medium']['min_devs']} THEN 'medium'
                WHEN c.gps_valid_count >= {gc['low']['min_gps_valid']}  THEN 'low'
                ELSE 'none'
            END AS gps_confidence,

            -- 信号置信度
            CASE
                WHEN c.signal_original_count >= {sc['high']['min_signal_original']} THEN 'high'
                WHEN c.signal_original_count >= {sc['medium']['min_signal_original']}  THEN 'medium'
                WHEN c.signal_original_count >= {sc['low']['min_signal_original']}  THEN 'low'
                ELSE 'none'
            END AS signal_confidence,

            -- Cell 规模
            CASE
                WHEN c.independent_obs >= {cs['major']['min_obs']} AND d.distinct_dev_id >= {cs['major']['min_devs']} THEN 'major'
                WHEN c.independent_obs >= {cs['large']['min_obs']} AND d.distinct_dev_id >= {cs['large']['min_devs']}  THEN 'large'
                WHEN c.independent_obs >= {cs['medium']['min_obs']} AND d.distinct_dev_id >= {cs['medium']['min_devs']}  THEN 'medium'
                WHEN c.independent_obs >= {cs['small']['min_obs']}  THEN 'small'
                ELSE 'micro'
            END AS cell_scale,

            -- 碰撞 / 动态标记
            COALESCE(dr.drift_pattern = 'collision', false) AS is_collision,
            COALESCE(dr.drift_max_spread_m > {dyn['min_spread_m']}
                 AND dr.drift_pattern IN ('migration', 'large_coverage'), false)
                AS is_dynamic,

            -- 生命周期
            CASE
                WHEN c.independent_obs < {lc['waiting']['min_obs']} OR d.distinct_dev_id < {lc['waiting']['min_devs']}
                    THEN 'waiting'
                WHEN c.independent_obs >= {lc['active']['min_obs']} AND d.distinct_dev_id >= {lc['active']['min_devs']}
                 AND COALESCE(r.p90_radius_m, 99999) < {lc['active']['max_p90_m']}
                 AND c.observed_span_hours >= {lc['active']['min_span_hours']}
                 AND COALESCE(dr.drift_pattern, '') != 'collision'
                    THEN 'active'
                ELSE 'observing'
            END AS lifecycle_state,

            -- 锚点资格
            (c.gps_valid_count >= {anc['min_gps_valid']}
             AND d.distinct_dev_id >= {anc['min_devs']}
             AND COALESCE(r.p90_radius_m, 99999) < {anc['max_p90_m']}
             AND c.observed_span_hours >= {anc['min_span_hours']}
             AND COALESCE(dr.drift_pattern, '') != 'collision'
            ) AS anchorable,

            -- 地理 (从 rebuild2 参考数据关联)
            geo.province_name,
            geo.city_name,
            geo.district_name

        FROM rebuild4._pf_cell_centroid c
        LEFT JOIN rebuild4._pf_cell_devs d    ON c.cell_id = d.cell_id
        LEFT JOIN rebuild4._pf_cell_radius r  ON c.cell_id = r.cell_id
        LEFT JOIN rebuild4._pf_bs_center bc   ON c.bs_id = bc.bs_id
        LEFT JOIN rebuild4._pf_cell_drift dr  ON c.cell_id = dr.cell_id
        LEFT JOIN (
            SELECT cell_id::text AS cell_id, province_name, city_name, district_name
            FROM rebuild4.sample_cell_profile
            WHERE province_name IS NOT NULL
        ) geo ON c.cell_id = geo.cell_id
    """)

    row = fetchone("""
        SELECT COUNT(*) AS cnt,
               COUNT(*) FILTER (WHERE lifecycle_state = 'active')    AS active,
               COUNT(*) FILTER (WHERE lifecycle_state = 'observing') AS observing,
               COUNT(*) FILTER (WHERE lifecycle_state = 'waiting')   AS waiting
        FROM rebuild4.etl_dim_cell
    """)
    return ProfileStepResult(
        step="build_cell", output_count=row["cnt"],
        details={"active": row["active"], "observing": row["observing"],
                 "waiting": row["waiting"]},
    )


# ============================================================
# Step 5: BS 画像 (聚合 Cell → BS)
# ============================================================

def _step5_build_bs(params: dict = None) -> ProfileStepResult:
    """从 etl_dim_cell 聚合构建 etl_dim_bs。"""
    if params is None:
        params = _load_params()
    bs_cls = params["bs_classification"]
    bs_lc = params.get("bs_lifecycle", {
        "active": {"min_excellent_cells": 1, "min_qualified_cells": 3},
        "observing": {"min_cells_with_gps": 1},
    })
    execute("DROP TABLE IF EXISTS rebuild4.etl_dim_bs")
    execute(f"""
        CREATE TABLE rebuild4.etl_dim_bs AS
        SELECT
            c.operator_code, c.operator_cn, c.lac, c.bs_id,
            MODE() WITHIN GROUP (ORDER BY c.tech_norm) AS tech_norm,

            COUNT(*)                           AS cell_count,
            SUM(c.record_count)                AS record_count,
            SUM(c.gps_valid_count)             AS gps_valid_count,
            MAX(c.distinct_dev_id)             AS total_devices,
            MAX(c.active_days)                 AS active_days,
            SUM(c.independent_obs)             AS independent_obs,

            -- BS 质心 = Cell 质心的中位数
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY c.center_lon) AS center_lon,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY c.center_lat) AS center_lat,

            -- BS P50/P90: Cell 质心到 BS 质心的距离分位
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY c.dist_to_bs_m) AS gps_p50_dist_m,
            PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY c.dist_to_bs_m) AS gps_p90_dist_m,

            -- 面积估算 (经纬度跨度)
            CASE WHEN COUNT(c.center_lon) >= 2 THEN
                (MAX(c.center_lon) - MIN(c.center_lon)) * 85300
              * (MAX(c.center_lat) - MIN(c.center_lat)) * 111000 / 1e6
            ELSE 0 END AS area_km2,

            -- 信号
            AVG(c.rsrp_avg)  AS rsrp_avg,
            AVG(c.rsrq_avg)  AS rsrq_avg,
            AVG(c.sinr_avg)  AS sinr_avg,

            -- 数据质量 (加权平均)
            CASE WHEN SUM(c.record_count) > 0 THEN
                SUM(c.record_count * COALESCE(c.gps_original_ratio, 0))
                / SUM(c.record_count)
            END AS gps_original_ratio,
            CASE WHEN SUM(c.record_count) > 0 THEN
                SUM(c.record_count * COALESCE(c.signal_original_ratio, 0))
                / SUM(c.record_count)
            END AS signal_original_ratio,

            -- Cell 分类统计
            COUNT(*) FILTER (WHERE c.is_collision)                 AS collision_cell_count,
            COUNT(*) FILTER (WHERE c.is_dynamic)                   AS dynamic_cell_count,
            COUNT(*) FILTER (WHERE c.drift_pattern = 'migration')  AS migration_cell_count,
            COUNT(*) FILTER (WHERE c.drift_pattern = 'large_coverage') AS large_coverage_cell_count,
            COUNT(*) FILTER (WHERE c.lifecycle_state = 'active')   AS active_cell_count,
            COUNT(*) FILTER (WHERE c.position_grade IN ('excellent', 'good')) AS good_cell_count,

            -- BS 分类
            CASE
                WHEN COUNT(*) FILTER (WHERE c.is_collision) > 0 THEN 'collision_bs'
                WHEN COUNT(*) FILTER (WHERE c.is_dynamic) > 0   THEN 'dynamic_bs'
                WHEN MAX(c.dist_to_bs_m) > {bs_cls['large_spread_min_dist_m']}                  THEN 'large_spread'
                ELSE 'normal_spread'
            END AS classification,

            -- BS 定位质量
            CASE
                WHEN COUNT(*) FILTER (WHERE c.gps_confidence IN ('high','medium')) >= 2
                    THEN 'good'
                WHEN COUNT(*) FILTER (WHERE c.gps_confidence != 'none') >= 1
                    THEN 'qualified'
                ELSE 'unqualified'
            END AS position_grade,

            -- 置信度 (取最高 Cell)
            CASE
                WHEN COUNT(*) FILTER (WHERE c.gps_confidence = 'high') > 0 THEN 'high'
                WHEN COUNT(*) FILTER (WHERE c.gps_confidence = 'medium') > 0 THEN 'medium'
                WHEN COUNT(*) FILTER (WHERE c.gps_confidence = 'low') > 0 THEN 'low'
                ELSE 'none'
            END AS gps_confidence,
            CASE
                WHEN COUNT(*) FILTER (WHERE c.signal_confidence = 'high') > 0 THEN 'high'
                WHEN COUNT(*) FILTER (WHERE c.signal_confidence = 'medium') > 0 THEN 'medium'
                WHEN COUNT(*) FILTER (WHERE c.signal_confidence = 'low') > 0 THEN 'low'
                ELSE 'none'
            END AS signal_confidence,

            -- 规模 (取 Cell 中最高)
            CASE
                WHEN COUNT(*) FILTER (WHERE c.cell_scale = 'major') > 0 THEN 'major'
                WHEN COUNT(*) FILTER (WHERE c.cell_scale = 'large') > 0 THEN 'large'
                WHEN COUNT(*) FILTER (WHERE c.cell_scale = 'medium') > 0 THEN 'medium'
                WHEN COUNT(*) FILTER (WHERE c.cell_scale = 'small') > 0 THEN 'small'
                ELSE 'micro'
            END AS cell_scale,

            -- BS 生命周期 (可配置规则: 1个优秀Cell或N个及格Cell)
            CASE
                WHEN COUNT(*) FILTER (WHERE c.position_grade = 'excellent') >= {bs_lc['active']['min_excellent_cells']}
                    THEN 'active'
                WHEN COUNT(*) FILTER (WHERE c.position_grade IN ('excellent','good','qualified')) >= {bs_lc['active']['min_qualified_cells']}
                    THEN 'active'
                WHEN COUNT(*) FILTER (WHERE c.gps_confidence != 'none') >= {bs_lc['observing']['min_cells_with_gps']}
                    THEN 'observing'
                ELSE 'waiting'
            END AS lifecycle_state,

            -- 锚点资格 (有 anchorable Cell)
            BOOL_OR(c.anchorable) AS anchorable,

            -- 地理 (取众数)
            MODE() WITHIN GROUP (ORDER BY c.province_name) AS province_name,
            MODE() WITHIN GROUP (ORDER BY c.city_name)     AS city_name,
            MODE() WITHIN GROUP (ORDER BY c.district_name) AS district_name,

            -- 多质心标记 (暂 false，后续可扩展)
            false AS is_multi_centroid

        FROM rebuild4.etl_dim_cell c
        GROUP BY c.operator_code, c.operator_cn, c.lac, c.bs_id
    """)

    row = fetchone("SELECT COUNT(*) AS cnt FROM rebuild4.etl_dim_bs")
    return ProfileStepResult(step="build_bs", output_count=row["cnt"])


# ============================================================
# Step 6: LAC 画像 (聚合 BS → LAC)
# ============================================================

def _step6_build_lac(params: dict = None) -> ProfileStepResult:
    """从 etl_dim_bs 聚合构建 etl_dim_lac。"""
    if params is None:
        params = _load_params()
    lac_lc = params.get("lac_lifecycle", {
        "active": {"min_active_bs": 3, "min_active_bs_ratio": 0.1},
        "observing": {"min_non_waiting_bs": 1},
    })
    execute("DROP TABLE IF EXISTS rebuild4.etl_dim_lac")
    execute(f"""
        CREATE TABLE rebuild4.etl_dim_lac AS
        SELECT
            b.operator_code, b.operator_cn, b.lac,
            MODE() WITHIN GROUP (ORDER BY b.tech_norm) AS tech_norm,

            COUNT(*)                     AS bs_count,
            SUM(b.cell_count)            AS cell_count,
            SUM(b.record_count)          AS record_count,
            SUM(b.total_devices)         AS total_devices,
            MAX(b.active_days)           AS active_days,
            SUM(b.independent_obs)       AS independent_obs,

            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY b.center_lon) AS center_lon,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY b.center_lat) AS center_lat,

            -- 面积
            CASE WHEN COUNT(b.center_lon) >= 2 THEN
                (MAX(b.center_lon) - MIN(b.center_lon)) * 85300
              * (MAX(b.center_lat) - MIN(b.center_lat)) * 111000 / 1e6
            ELSE 0 END AS area_km2,

            AVG(b.rsrp_avg) AS rsrp_avg,
            CASE WHEN SUM(b.record_count) > 0 THEN
                SUM(b.gps_valid_count)::float / SUM(b.record_count)
            END AS gps_original_ratio,
            CASE WHEN SUM(b.record_count) > 0 THEN
                SUM(b.record_count * COALESCE(b.signal_original_ratio, 0))
                / SUM(b.record_count)
            END AS signal_original_ratio,

            -- BS 异常统计
            COUNT(*) FILTER (WHERE b.classification = 'collision_bs')  AS collision_bs_count,
            COUNT(*) FILTER (WHERE b.classification = 'dynamic_bs')    AS dynamic_bs_count,
            COUNT(*) FILTER (WHERE b.classification = 'large_spread')  AS large_spread_bs_count,
            COUNT(*) FILTER (WHERE b.lifecycle_state = 'active')       AS active_bs_count,
            CASE WHEN COUNT(*) > 0 THEN
                COUNT(*) FILTER (WHERE b.classification IN ('collision_bs', 'dynamic_bs', 'large_spread'))::float
                / COUNT(*)
            END AS anomaly_bs_ratio,

            CASE
                WHEN COUNT(*) FILTER (WHERE b.position_grade = 'good') > 0 THEN 'good'
                WHEN COUNT(*) FILTER (WHERE b.position_grade = 'qualified') > 0 THEN 'qualified'
                ELSE 'unqualified'
            END AS position_grade,

            -- LAC 生命周期 (可配置: 需要足够多 active BS)
            CASE
                WHEN COUNT(*) FILTER (WHERE b.lifecycle_state = 'active') >= {lac_lc['active']['min_active_bs']}
                  OR (COUNT(*) > 0 AND COUNT(*) FILTER (WHERE b.lifecycle_state = 'active')::float / COUNT(*) >= {lac_lc['active']['min_active_bs_ratio']})
                    THEN 'active'
                WHEN COUNT(*) FILTER (WHERE b.lifecycle_state != 'waiting') >= {lac_lc['observing']['min_non_waiting_bs']}
                    THEN 'observing'
                ELSE 'waiting'
            END AS lifecycle_state,

            MODE() WITHIN GROUP (ORDER BY b.province_name) AS province_name,
            MODE() WITHIN GROUP (ORDER BY b.city_name)     AS city_name,
            MODE() WITHIN GROUP (ORDER BY b.district_name) AS district_name

        FROM rebuild4.etl_dim_bs b
        GROUP BY b.operator_code, b.operator_cn, b.lac
    """)

    row = fetchone("SELECT COUNT(*) AS cnt FROM rebuild4.etl_dim_lac")
    return ProfileStepResult(step="build_lac", output_count=row["cnt"])


# ============================================================
# Streaming 模式
# ============================================================

def run_profile_streaming(date_windows: list[str] = None,
                          params_path: str = None) -> ProfileResult:
    """按天累积运行 streaming 模式，产出 snapshot 序列和 diff。

    每个窗口使用 etl_filled 中 <= end_date 的累积数据，
    复用 _step1~_step6 的同一算法链路。
    最后一个窗口的结果保留在 etl_dim_cell / etl_dim_bs / etl_dim_lac。
    """
    import uuid
    from datetime import datetime

    import hashlib, json

    params = _load_params(params_path)
    params_hash = hashlib.md5(json.dumps(params, sort_keys=True).encode()).hexdigest()[:8]
    profile_run_id = uuid.uuid4().hex[:8]

    # 自动检测日期窗口
    if date_windows is None:
        rows = fetchall("""
            SELECT DISTINCT DATE(ts_std)::text AS d
            FROM rebuild4.etl_filled ORDER BY d
        """)
        date_windows = [r["d"] for r in rows]

    _ensure_stream_tables()
    _ensure_bs_lac_stream_tables()
    _ensure_run_log_table()

    # 写入 run log (running)
    execute("""
        INSERT INTO rebuild4_meta.etl_profile_run_log (
            profile_run_id, mode, window_granularity, source_table,
            source_date_from, source_date_to, params_path, params_hash,
            started_at, status
        ) VALUES (%s, 'streaming', 'daily', 'rebuild4.etl_filled',
                  %s::date, %s::date, %s, %s, NOW(), 'running')
    """, (profile_run_id, date_windows[0], date_windows[-1],
          params_path or str(_DEFAULT_PARAMS_PATH), params_hash))

    # 清除本次 run 的旧数据（如有）
    for tbl in ("etl_profile_snapshot", "etl_profile_snapshot_cell",
                "etl_profile_snapshot_diff",
                "etl_profile_snapshot_bs", "etl_profile_snapshot_lac",
                "etl_profile_snapshot_diff_bs", "etl_profile_snapshot_diff_lac"):
        execute(f"DELETE FROM rebuild4_meta.{tbl} WHERE profile_run_id = %s",
                (profile_run_id,))

    result = ProfileResult()

    for i, end_date in enumerate(date_windows):
        seq = i + 1
        label = f"Day {seq}"

        # 复用现有 6 步，仅 step1/step2 加日期窗口
        _step1_independent_obs(end_date=end_date)
        _step2_cell_centroid_radius(end_date=end_date)
        _step3_drift_analysis(params)
        r4 = _step4_build_cell(params)
        _step5_build_bs(params)
        _step6_build_lac(params)

        # 落盘 Cell/BS/LAC snapshot
        _save_snapshot(profile_run_id, seq, label, end_date)
        _save_snapshot_cells(profile_run_id, seq)
        _save_snapshot_bs(profile_run_id, seq)
        _save_snapshot_lac(profile_run_id, seq)

        # 计算与上一个 snapshot 的 diff (Cell + BS + LAC)
        if seq > 1:
            _save_diff(profile_run_id, seq - 1, seq)
            _save_diff_bs(profile_run_id, seq - 1, seq)
            _save_diff_lac(profile_run_id, seq - 1, seq)

        _cleanup_intermediates()

    # 记录最终结果
    final = fetchone("""
        SELECT COUNT(*) AS cnt,
               COUNT(*) FILTER (WHERE lifecycle_state = 'active')    AS active,
               COUNT(*) FILTER (WHERE lifecycle_state = 'observing') AS observing,
               COUNT(*) FILTER (WHERE lifecycle_state = 'waiting')   AS waiting
        FROM rebuild4.etl_dim_cell
    """)
    result.cell_count = final["cnt"]
    result.bs_count = fetchone("SELECT COUNT(*) AS cnt FROM rebuild4.etl_dim_bs")["cnt"]
    result.lac_count = fetchone("SELECT COUNT(*) AS cnt FROM rebuild4.etl_dim_lac")["cnt"]

    # 完成 run log，设为 current
    execute("UPDATE rebuild4_meta.etl_profile_run_log SET is_current = false WHERE is_current = true")
    execute("""
        UPDATE rebuild4_meta.etl_profile_run_log
        SET finished_at = NOW(), status = 'completed',
            snapshot_count = %s, final_cell_count = %s,
            final_bs_count = %s, final_lac_count = %s,
            is_current = true
        WHERE profile_run_id = %s
    """, (len(date_windows), result.cell_count, result.bs_count,
          result.lac_count, profile_run_id))

    return result


def _ensure_run_log_table():
    """创建 profile run log 表（如不存在）。"""
    execute("""
        CREATE TABLE IF NOT EXISTS rebuild4_meta.etl_profile_run_log (
            profile_run_id TEXT PRIMARY KEY,
            mode           TEXT NOT NULL,
            window_granularity TEXT DEFAULT 'daily',
            source_table   TEXT DEFAULT 'rebuild4.etl_filled',
            source_date_from DATE,
            source_date_to   DATE,
            params_path    TEXT,
            params_hash    TEXT,
            started_at     TIMESTAMPTZ,
            finished_at    TIMESTAMPTZ,
            status         TEXT DEFAULT 'running',
            snapshot_count INT,
            final_cell_count INT,
            final_bs_count   INT,
            final_lac_count  INT,
            is_current     BOOLEAN DEFAULT false
        )
    """)


def _ensure_stream_tables():
    """创建 streaming snapshot 落盘表（如不存在）。"""
    execute("""
        CREATE TABLE IF NOT EXISTS rebuild4_meta.etl_profile_snapshot (
            profile_run_id TEXT NOT NULL,
            snapshot_seq   INT NOT NULL,
            snapshot_label TEXT,
            window_end_date DATE,
            stream_cell_count INT,
            active_count      INT,
            observing_count   INT,
            waiting_count     INT,
            anchorable_count  INT,
            bs_count          INT,
            lac_count         INT,
            cell_coverage_pct  NUMERIC,
            cell_centroid_median_m NUMERIC,
            active_recall_pct  NUMERIC,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (profile_run_id, snapshot_seq)
        )
    """)
    execute("""
        CREATE TABLE IF NOT EXISTS rebuild4_meta.etl_profile_snapshot_cell (
            profile_run_id TEXT NOT NULL,
            snapshot_seq   INT NOT NULL,
            cell_id        TEXT NOT NULL,
            bs_id          TEXT,
            lac            TEXT,
            lifecycle_state TEXT,
            anchorable     BOOLEAN,
            center_lon     NUMERIC,
            center_lat     NUMERIC,
            p50_radius_m   NUMERIC,
            p90_radius_m   NUMERIC,
            position_grade TEXT,
            drift_pattern  TEXT,
            PRIMARY KEY (profile_run_id, snapshot_seq, cell_id)
        )
    """)
    execute("""
        CREATE TABLE IF NOT EXISTS rebuild4_meta.etl_profile_snapshot_diff (
            profile_run_id TEXT NOT NULL,
            from_seq       INT NOT NULL,
            to_seq         INT NOT NULL,
            cell_id        TEXT NOT NULL,
            diff_kind      TEXT,
            from_lifecycle_state TEXT,
            to_lifecycle_state   TEXT,
            centroid_shift_m     NUMERIC,
            p90_delta_m          NUMERIC,
            anchorable_changed   BOOLEAN,
            PRIMARY KEY (profile_run_id, from_seq, to_seq, cell_id)
        )
    """)


def _save_snapshot(profile_run_id: str, seq: int, label: str, end_date: str):
    """保存单个 snapshot 的汇总指标。"""
    execute("""
        INSERT INTO rebuild4_meta.etl_profile_snapshot (
            profile_run_id, snapshot_seq, snapshot_label, window_end_date,
            stream_cell_count, active_count, observing_count, waiting_count,
            anchorable_count, bs_count, lac_count
        )
        SELECT
            %s, %s, %s, %s::date,
            COUNT(*),
            COUNT(*) FILTER (WHERE lifecycle_state = 'active'),
            COUNT(*) FILTER (WHERE lifecycle_state = 'observing'),
            COUNT(*) FILTER (WHERE lifecycle_state = 'waiting'),
            COUNT(*) FILTER (WHERE anchorable),
            (SELECT COUNT(*) FROM rebuild4.etl_dim_bs),
            (SELECT COUNT(*) FROM rebuild4.etl_dim_lac)
        FROM rebuild4.etl_dim_cell
    """, (profile_run_id, seq, label, end_date))


def _save_snapshot_cells(profile_run_id: str, seq: int):
    """保存单个 snapshot 的 Cell 级状态。"""
    execute("""
        INSERT INTO rebuild4_meta.etl_profile_snapshot_cell (
            profile_run_id, snapshot_seq, cell_id, bs_id, lac,
            lifecycle_state, anchorable, center_lon, center_lat,
            p50_radius_m, p90_radius_m, position_grade, drift_pattern
        )
        SELECT
            %s, %s, cell_id, bs_id, lac,
            lifecycle_state, anchorable, center_lon, center_lat,
            p50_radius_m, p90_radius_m, position_grade, drift_pattern
        FROM rebuild4.etl_dim_cell
    """, (profile_run_id, seq))


def _save_diff(profile_run_id: str, from_seq: int, to_seq: int):
    """计算并保存相邻 snapshot 的 Cell 级 diff。"""
    execute("""
        INSERT INTO rebuild4_meta.etl_profile_snapshot_diff (
            profile_run_id, from_seq, to_seq, cell_id, diff_kind,
            from_lifecycle_state, to_lifecycle_state,
            centroid_shift_m, p90_delta_m, anchorable_changed
        )
        -- 新增的 Cell
        SELECT
            %s, %s, %s, cur.cell_id, 'added',
            NULL::text, cur.lifecycle_state,
            NULL::numeric, NULL::numeric, NULL::boolean
        FROM rebuild4_meta.etl_profile_snapshot_cell cur
        LEFT JOIN rebuild4_meta.etl_profile_snapshot_cell prev
          ON prev.profile_run_id = cur.profile_run_id
         AND prev.snapshot_seq = %s
         AND prev.cell_id = cur.cell_id
        WHERE cur.profile_run_id = %s AND cur.snapshot_seq = %s
          AND prev.cell_id IS NULL

        UNION ALL

        -- 移除的 Cell
        SELECT
            %s, %s, %s, prev.cell_id, 'removed',
            prev.lifecycle_state, NULL::text,
            NULL::numeric, NULL::numeric, NULL::boolean
        FROM rebuild4_meta.etl_profile_snapshot_cell prev
        LEFT JOIN rebuild4_meta.etl_profile_snapshot_cell cur
          ON cur.profile_run_id = prev.profile_run_id
         AND cur.snapshot_seq = %s
         AND cur.cell_id = prev.cell_id
        WHERE prev.profile_run_id = %s AND prev.snapshot_seq = %s
          AND cur.cell_id IS NULL

        UNION ALL

        -- 变化的 Cell (lifecycle 或 anchorable 变化，或质心位移)
        SELECT
            %s, %s, %s, cur.cell_id,
            CASE WHEN prev.lifecycle_state != cur.lifecycle_state
                   OR prev.anchorable != cur.anchorable THEN 'changed'
                 ELSE 'unchanged' END,
            prev.lifecycle_state, cur.lifecycle_state,
            CASE WHEN prev.center_lon IS NOT NULL AND cur.center_lon IS NOT NULL THEN
                SQRT(POWER((cur.center_lon - prev.center_lon) * 85300, 2)
                   + POWER((cur.center_lat - prev.center_lat) * 111000, 2))
            END,
            cur.p90_radius_m - prev.p90_radius_m,
            prev.anchorable IS DISTINCT FROM cur.anchorable
        FROM rebuild4_meta.etl_profile_snapshot_cell cur
        JOIN rebuild4_meta.etl_profile_snapshot_cell prev
          ON prev.profile_run_id = cur.profile_run_id
         AND prev.snapshot_seq = %s
         AND prev.cell_id = cur.cell_id
        WHERE cur.profile_run_id = %s AND cur.snapshot_seq = %s
    """, (
        # added
        profile_run_id, from_seq, to_seq, from_seq, profile_run_id, to_seq,
        # removed
        profile_run_id, from_seq, to_seq, to_seq, profile_run_id, from_seq,
        # changed/unchanged
        profile_run_id, from_seq, to_seq, from_seq, profile_run_id, to_seq,
    ))


# ============================================================
# BS/LAC snapshot 落盘
# ============================================================

def _ensure_bs_lac_stream_tables():
    """创建 BS/LAC streaming snapshot 表（如不存在）。"""
    execute("""
        CREATE TABLE IF NOT EXISTS rebuild4_meta.etl_profile_snapshot_bs (
            profile_run_id TEXT NOT NULL,
            snapshot_seq   INT NOT NULL,
            operator_code  TEXT NOT NULL,
            lac            TEXT NOT NULL,
            bs_id          TEXT NOT NULL,
            cell_count     INT,
            active_cell_count   INT,
            good_cell_count     INT,
            lifecycle_state     TEXT,
            anchorable          BOOLEAN,
            classification      TEXT,
            center_lon          NUMERIC,
            center_lat          NUMERIC,
            gps_p90_dist_m      NUMERIC,
            position_grade      TEXT,
            PRIMARY KEY (profile_run_id, snapshot_seq, operator_code, lac, bs_id)
        )
    """)
    execute("""
        CREATE TABLE IF NOT EXISTS rebuild4_meta.etl_profile_snapshot_lac (
            profile_run_id TEXT NOT NULL,
            snapshot_seq   INT NOT NULL,
            operator_code  TEXT NOT NULL,
            lac            TEXT NOT NULL,
            bs_count       INT,
            active_bs_count    INT,
            cell_count         INT,
            lifecycle_state    TEXT,
            center_lon         NUMERIC,
            center_lat         NUMERIC,
            area_km2           NUMERIC,
            anomaly_bs_ratio   NUMERIC,
            position_grade     TEXT,
            PRIMARY KEY (profile_run_id, snapshot_seq, operator_code, lac)
        )
    """)
    execute("""
        CREATE TABLE IF NOT EXISTS rebuild4_meta.etl_profile_snapshot_diff_bs (
            profile_run_id TEXT NOT NULL,
            from_seq       INT NOT NULL,
            to_seq         INT NOT NULL,
            operator_code  TEXT NOT NULL,
            lac            TEXT NOT NULL,
            bs_id          TEXT NOT NULL,
            diff_kind      TEXT,
            from_lifecycle_state TEXT,
            to_lifecycle_state   TEXT,
            cell_count_delta     INT,
            active_cell_delta    INT,
            anchorable_changed   BOOLEAN,
            PRIMARY KEY (profile_run_id, from_seq, to_seq, operator_code, lac, bs_id)
        )
    """)
    execute("""
        CREATE TABLE IF NOT EXISTS rebuild4_meta.etl_profile_snapshot_diff_lac (
            profile_run_id TEXT NOT NULL,
            from_seq       INT NOT NULL,
            to_seq         INT NOT NULL,
            operator_code  TEXT NOT NULL,
            lac            TEXT NOT NULL,
            diff_kind      TEXT,
            from_lifecycle_state TEXT,
            to_lifecycle_state   TEXT,
            bs_count_delta       INT,
            active_bs_delta      INT,
            PRIMARY KEY (profile_run_id, from_seq, to_seq, operator_code, lac)
        )
    """)


def _save_snapshot_bs(profile_run_id: str, seq: int):
    """保存单个 snapshot 的 BS 级状态。"""
    execute("""
        INSERT INTO rebuild4_meta.etl_profile_snapshot_bs (
            profile_run_id, snapshot_seq, operator_code, lac, bs_id,
            cell_count, active_cell_count, good_cell_count,
            lifecycle_state, anchorable, classification,
            center_lon, center_lat, gps_p90_dist_m, position_grade
        )
        SELECT
            %s, %s, operator_code, lac, bs_id,
            cell_count, active_cell_count, good_cell_count,
            lifecycle_state, anchorable, classification,
            center_lon, center_lat, gps_p90_dist_m, position_grade
        FROM rebuild4.etl_dim_bs
        WHERE bs_id IS NOT NULL AND operator_code IS NOT NULL AND lac IS NOT NULL
    """, (profile_run_id, seq))


def _save_snapshot_lac(profile_run_id: str, seq: int):
    """保存单个 snapshot 的 LAC 级状态。"""
    execute("""
        INSERT INTO rebuild4_meta.etl_profile_snapshot_lac (
            profile_run_id, snapshot_seq, lac, operator_code,
            bs_count, active_bs_count, cell_count,
            lifecycle_state, center_lon, center_lat,
            area_km2, anomaly_bs_ratio, position_grade
        )
        SELECT
            %s, %s, lac, operator_code,
            bs_count, active_bs_count, cell_count,
            lifecycle_state, center_lon, center_lat,
            area_km2, anomaly_bs_ratio, position_grade
        FROM rebuild4.etl_dim_lac
        WHERE lac IS NOT NULL AND operator_code IS NOT NULL
    """, (profile_run_id, seq))


def _save_diff_bs(profile_run_id: str, from_seq: int, to_seq: int):
    """计算 BS 级 diff。"""
    execute("""
        INSERT INTO rebuild4_meta.etl_profile_snapshot_diff_bs (
            profile_run_id, from_seq, to_seq, operator_code, lac, bs_id, diff_kind,
            from_lifecycle_state, to_lifecycle_state,
            cell_count_delta, active_cell_delta, anchorable_changed
        )
        -- 新增 BS
        SELECT %s, %s, %s, cur.operator_code, cur.lac, cur.bs_id, 'added',
            NULL, cur.lifecycle_state, cur.cell_count, cur.active_cell_count, NULL
        FROM rebuild4_meta.etl_profile_snapshot_bs cur
        LEFT JOIN rebuild4_meta.etl_profile_snapshot_bs prev
          ON prev.profile_run_id = cur.profile_run_id AND prev.snapshot_seq = %s
         AND prev.operator_code = cur.operator_code AND prev.lac = cur.lac AND prev.bs_id = cur.bs_id
        WHERE cur.profile_run_id = %s AND cur.snapshot_seq = %s AND prev.bs_id IS NULL
        UNION ALL
        -- 变化/不变 BS
        SELECT %s, %s, %s, cur.operator_code, cur.lac, cur.bs_id,
            CASE WHEN prev.lifecycle_state != cur.lifecycle_state THEN 'changed' ELSE 'unchanged' END,
            prev.lifecycle_state, cur.lifecycle_state,
            cur.cell_count - prev.cell_count,
            cur.active_cell_count - prev.active_cell_count,
            prev.anchorable IS DISTINCT FROM cur.anchorable
        FROM rebuild4_meta.etl_profile_snapshot_bs cur
        JOIN rebuild4_meta.etl_profile_snapshot_bs prev
          ON prev.profile_run_id = cur.profile_run_id AND prev.snapshot_seq = %s
         AND prev.operator_code = cur.operator_code AND prev.lac = cur.lac AND prev.bs_id = cur.bs_id
        WHERE cur.profile_run_id = %s AND cur.snapshot_seq = %s
    """, (
        profile_run_id, from_seq, to_seq, from_seq, profile_run_id, to_seq,
        profile_run_id, from_seq, to_seq, from_seq, profile_run_id, to_seq,
    ))


def _save_diff_lac(profile_run_id: str, from_seq: int, to_seq: int):
    """计算 LAC 级 diff。"""
    execute("""
        INSERT INTO rebuild4_meta.etl_profile_snapshot_diff_lac (
            profile_run_id, from_seq, to_seq, operator_code, lac, diff_kind,
            from_lifecycle_state, to_lifecycle_state,
            bs_count_delta, active_bs_delta
        )
        -- 新增 LAC
        SELECT %s, %s, %s, cur.operator_code, cur.lac, 'added',
            NULL, cur.lifecycle_state, cur.bs_count, cur.active_bs_count
        FROM rebuild4_meta.etl_profile_snapshot_lac cur
        LEFT JOIN rebuild4_meta.etl_profile_snapshot_lac prev
          ON prev.profile_run_id = cur.profile_run_id AND prev.snapshot_seq = %s
         AND prev.operator_code = cur.operator_code AND prev.lac = cur.lac
        WHERE cur.profile_run_id = %s AND cur.snapshot_seq = %s AND prev.lac IS NULL
        UNION ALL
        -- 变化/不变 LAC
        SELECT %s, %s, %s, cur.operator_code, cur.lac,
            CASE WHEN prev.lifecycle_state != cur.lifecycle_state THEN 'changed' ELSE 'unchanged' END,
            prev.lifecycle_state, cur.lifecycle_state,
            cur.bs_count - prev.bs_count,
            cur.active_bs_count - prev.active_bs_count
        FROM rebuild4_meta.etl_profile_snapshot_lac cur
        JOIN rebuild4_meta.etl_profile_snapshot_lac prev
          ON prev.profile_run_id = cur.profile_run_id AND prev.snapshot_seq = %s
         AND prev.operator_code = cur.operator_code AND prev.lac = cur.lac
        WHERE cur.profile_run_id = %s AND cur.snapshot_seq = %s
    """, (
        profile_run_id, from_seq, to_seq, from_seq, profile_run_id, to_seq,
        profile_run_id, from_seq, to_seq, from_seq, profile_run_id, to_seq,
    ))


# ============================================================
# 清理中间表
# ============================================================

def _cleanup_intermediates():
    for t in ("_pf_obs", "_pf_cell_centroid", "_pf_cell_devs",
              "_pf_cell_radius", "_pf_bs_center",
              "_pf_daily_centroid", "_pf_cell_drift"):
        execute(f"DROP TABLE IF EXISTS rebuild4.{t}")
