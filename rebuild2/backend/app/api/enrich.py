"""Phase 3 数据补齐与修正 API：BS 精算 → Cell GPS 校验 → 明细 GPS 修正 → 信号补齐 → 回算。

Part A（正常数据处理）：
  Step 1: BS 中心点精算 — 信号加权选种 + 设备去重 + 分箱中位数 + 异常剔除
  Step 2: Cell GPS 校验与修正
  Step 3: 明细行 GPS 修正
  Step 4: 信号补齐（二阶段）
  Step 5: 回算

大表操作通过 SSH psql 在服务器上执行，结果写中间表，本 API 读中间表。
"""

from __future__ import annotations

import asyncio
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

router = APIRouter(prefix="/enrich", tags=["enrich"])

# ─── SSH 配置 ──────────────────────────────────────────────
SSH_HOST = "192.168.200.217"
SSH_USER = "root"
SSH_PASS = "111111"
DB_NAME = "ip_loc2"

# ─── 后台任务追踪 ──────────────────────────────────────────
_tasks: dict[str, asyncio.Task] = {}
_task_results: dict[str, dict] = {}


async def _ssh_psql(sql: str) -> dict:
    """通过 SSH 在服务器上执行 psql，返回 returncode / stdout / stderr。"""
    proc = await asyncio.create_subprocess_exec(
        "sshpass", "-p", SSH_PASS,
        "ssh", "-o", "StrictHostKeyChecking=no", "-o", "PubkeyAuthentication=no",
        f"{SSH_USER}@{SSH_HOST}",
        "psql", "-h", "localhost", "-p", "5433",
        "-U", "postgres", "-d", DB_NAME,
        "-v", "ON_ERROR_STOP=1",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate(input=sql.encode("utf-8"))
    return {
        "returncode": proc.returncode,
        "stdout": stdout.decode(errors="replace")[-3000:],
        "stderr": stderr.decode(errors="replace")[-3000:],
    }


def _table_exists_sql(name: str) -> str:
    return (
        "SELECT EXISTS ("
        "  SELECT 1 FROM information_schema.tables"
        f"  WHERE table_schema = 'rebuild2' AND table_name = '{name}'"
        ") AS ok"
    )


# ═══════════════════════════════════════════════════════════
#  Step 1：BS 中心点精算
# ═══════════════════════════════════════════════════════════

STEP1_PARAMS = {
    "device_dedup_threshold": 100,
    "seed_tiers": [
        {"min_points": 50, "take": 50},
        {"min_points": 20, "take": 20},
        {"min_points": 5, "take": "top 80%"},
        {"min_points": 0, "take": "全部"},
    ],
    "outlier_distance_m": 2500,
    "quality_rules": {
        "Usable": "≥2 个 Cell 有 GPS",
        "Risk": "仅 1 个 Cell 有 GPS",
        "Unusable": "0 个 Cell 有 GPS",
    },
    "rsrp_invalid_values": [-1, -110, "≥0"],
    "gps_bounds": "经度 73~135, 纬度 3~54（中国范围）",
    "distance_approx": "1° 经度 ≈ 85.3km, 1° 纬度 ≈ 111km（北京附近）",
    "binning_precision": "round(lon*10000) ≈ 11m 精度",
}


@router.get("/step1/preview")
async def step1_preview(db: AsyncSession = Depends(get_db)):
    """Step 1 预览：当前 BS GPS 质量概览 + 算法参数。"""

    # GPS 覆盖概览
    gps_result = await db.execute(text("""
        SELECT
            count(*) AS total_bs,
            count(*) FILTER (WHERE gps_center_lon IS NOT NULL) AS bs_with_center,
            count(*) FILTER (WHERE gps_center_lon IS NULL) AS bs_no_center,
            count(*) FILTER (WHERE valid_gps_count > 0) AS bs_with_gps_points,
            ROUND(AVG(valid_gps_count) FILTER (WHERE valid_gps_count > 0)::numeric, 0) AS avg_gps_per_bs,
            SUM(valid_gps_count)::bigint AS total_gps_points
        FROM rebuild2.dim_bs_stats
    """))
    gps_overview = dict(gps_result.mappings().first())

    # 预估 GPS 质量分级（基于 Cell GPS 覆盖）
    quality_result = await db.execute(text("""
        WITH bs_cell_gps AS (
            SELECT operator_code, tech_norm, lac, bs_id,
                count(*) FILTER (WHERE gps_center_lon IS NOT NULL) AS cells_with_gps
            FROM rebuild2.dim_cell_stats
            GROUP BY operator_code, tech_norm, lac, bs_id
        )
        SELECT
            count(*) AS total,
            count(*) FILTER (WHERE cells_with_gps >= 2) AS usable,
            count(*) FILTER (WHERE cells_with_gps = 1) AS risk,
            count(*) FILTER (WHERE cells_with_gps = 0) AS unusable
        FROM bs_cell_gps
    """))
    quality_preview = dict(quality_result.mappings().first())

    # 按运营商+制式
    by_op_result = await db.execute(text("""
        SELECT operator_cn, tech_norm,
            count(*) AS bs_count,
            count(*) FILTER (WHERE valid_gps_count > 0) AS bs_with_gps,
            sum(valid_gps_count)::bigint AS total_gps_points,
            sum(cell_count)::bigint AS total_cells
        FROM rebuild2.dim_bs_stats
        GROUP BY operator_cn, tech_norm
        ORDER BY total_gps_points DESC NULLS LAST
    """))
    by_operator = [dict(r) for r in by_op_result.mappings().all()]

    return {
        "params": STEP1_PARAMS,
        "gps_overview": gps_overview,
        "quality_preview": quality_preview,
        "by_operator": by_operator,
        "data_quality_note": {
            "gps_coverage": "84.2%（可信 LAC 范围内 l0_lac GPS 有效）",
            "rsrp_coverage": "88.9%（RSRP 非空）",
            "gps_and_rsrp": "约 75% 记录同时有 GPS 和有效 RSRP",
        },
    }


@router.post("/step1/execute")
async def step1_execute():
    """启动 Step 1 BS 中心点精算（后台 SSH psql 执行）。"""
    task_key = "step1"
    if task_key in _tasks and not _tasks[task_key].done():
        return {"ok": False, "error": "Step 1 正在执行中，请等待完成"}

    sql = _build_step1_sql()

    async def run():
        result = await _ssh_psql(sql)
        _task_results[task_key] = result
        return result

    _tasks[task_key] = asyncio.create_task(run())
    return {"ok": True, "message": "Step 1 已启动，请轮询 /step1/status 查看进度"}


@router.get("/step1/status")
async def step1_status(db: AsyncSession = Depends(get_db)):
    """检查 Step 1 执行状态。"""
    task_key = "step1"
    task = _tasks.get(task_key)

    # 任务正在执行
    if task and not task.done():
        return {"status": "running", "message": "BS 中心点精算执行中..."}

    # 任务完成，检查结果
    if task and task.done():
        try:
            result = task.result()
        except Exception as e:
            return {"status": "error", "message": str(e)}

        if result["returncode"] != 0:
            return {
                "status": "error",
                "message": "SQL 执行失败",
                "stderr": result["stderr"],
                "stdout": result["stdout"],
            }

    # 检查表是否存在
    check = await db.execute(text(_table_exists_sql("dim_bs_refined")))
    exists = dict(check.mappings().first())["ok"]
    if not exists:
        return {"status": "not_started", "message": "dim_bs_refined 尚未创建"}

    return {"status": "done", "message": "dim_bs_refined 已就绪"}


@router.get("/step1/result")
async def step1_result(db: AsyncSession = Depends(get_db)):
    """读取 dim_bs_refined 精算结果。"""
    check = await db.execute(text(_table_exists_sql("dim_bs_refined")))
    if not dict(check.mappings().first())["ok"]:
        return {"exists": False}

    # 总览
    total_result = await db.execute(text("""
        SELECT
            count(*) AS total_bs,
            count(*) FILTER (WHERE gps_quality = 'Usable') AS usable,
            count(*) FILTER (WHERE gps_quality = 'Risk') AS risk,
            count(*) FILTER (WHERE gps_quality = 'Unusable') AS unusable,
            count(*) FILTER (WHERE gps_center_lon IS NOT NULL) AS has_center,
            count(*) FILTER (WHERE had_outlier_removal) AS outlier_removed,
            ROUND(AVG(gps_p50_dist_m) FILTER (WHERE gps_p50_dist_m IS NOT NULL)::numeric, 0) AS avg_p50,
            ROUND(AVG(gps_p90_dist_m) FILTER (WHERE gps_p90_dist_m IS NOT NULL)::numeric, 0) AS avg_p90
        FROM rebuild2.dim_bs_refined
    """))
    totals = dict(total_result.mappings().first())

    # 按运营商+制式
    by_op_result = await db.execute(text("""
        SELECT operator_cn, tech_norm,
            count(*) AS bs_count,
            count(*) FILTER (WHERE gps_quality = 'Usable') AS usable,
            count(*) FILTER (WHERE gps_quality = 'Risk') AS risk,
            count(*) FILTER (WHERE gps_quality = 'Unusable') AS unusable,
            ROUND(AVG(gps_p50_dist_m) FILTER (WHERE gps_p50_dist_m IS NOT NULL)::numeric, 0) AS avg_p50,
            ROUND(AVG(gps_p90_dist_m) FILTER (WHERE gps_p90_dist_m IS NOT NULL)::numeric, 0) AS avg_p90
        FROM rebuild2.dim_bs_refined
        GROUP BY operator_cn, tech_norm
        ORDER BY bs_count DESC
    """))
    by_operator = [dict(r) for r in by_op_result.mappings().all()]

    # 距离分布
    dist_result = await db.execute(text("""
        SELECT
            count(*) FILTER (WHERE gps_p90_dist_m <= 500) AS p90_le_500,
            count(*) FILTER (WHERE gps_p90_dist_m > 500 AND gps_p90_dist_m <= 1000) AS p90_500_1000,
            count(*) FILTER (WHERE gps_p90_dist_m > 1000 AND gps_p90_dist_m <= 1500) AS p90_1000_1500,
            count(*) FILTER (WHERE gps_p90_dist_m > 1500 AND gps_p90_dist_m <= 2500) AS p90_1500_2500,
            count(*) FILTER (WHERE gps_p90_dist_m > 2500) AS p90_gt_2500
        FROM rebuild2.dim_bs_refined
        WHERE gps_p90_dist_m IS NOT NULL
    """))
    dist_distribution = dict(dist_result.mappings().first())

    # 与旧中心点对比
    drift_result = await db.execute(text("""
        SELECT
            count(*) AS total_compared,
            count(*) FILTER (WHERE
                SQRT(POWER((gps_center_lon - old_center_lon) * 85300, 2) +
                     POWER((gps_center_lat - old_center_lat) * 111000, 2)) > 100
            ) AS drifted_gt_100m,
            count(*) FILTER (WHERE
                SQRT(POWER((gps_center_lon - old_center_lon) * 85300, 2) +
                     POWER((gps_center_lat - old_center_lat) * 111000, 2)) > 500
            ) AS drifted_gt_500m,
            ROUND(AVG(
                SQRT(POWER((gps_center_lon - old_center_lon) * 85300, 2) +
                     POWER((gps_center_lat - old_center_lat) * 111000, 2))
            )::numeric, 0) AS avg_drift_m
        FROM rebuild2.dim_bs_refined
        WHERE gps_center_lon IS NOT NULL AND old_center_lon IS NOT NULL
    """))
    center_drift = dict(drift_result.mappings().first())

    # Top 30 BS
    detail_result = await db.execute(text("""
        SELECT operator_cn, tech_norm, lac, bs_id, cell_count,
            record_count, cells_with_gps, total_gps_points, seed_count,
            gps_center_lon, gps_center_lat,
            gps_p50_dist_m, gps_p90_dist_m, gps_max_dist_m,
            gps_quality, had_outlier_removal,
            old_center_lon, old_center_lat
        FROM rebuild2.dim_bs_refined
        WHERE gps_center_lon IS NOT NULL
        ORDER BY record_count DESC LIMIT 30
    """))
    items = [dict(r) for r in detail_result.mappings().all()]

    return {
        "exists": True,
        "totals": totals,
        "by_operator": by_operator,
        "dist_distribution": dist_distribution,
        "center_drift": center_drift,
        "items": items,
    }


# ─── Step 1 SQL 生成 ──────────────────────────────────────

def _build_step1_sql() -> str:
    """生成 Step 1 BS 中心点精算的完整 SQL 脚本。

    优化要点：
    - 禁用并行查询（避免 PG 共享内存段扩展失败）
    - 异常剔除拆为物化距离表 + 分支处理（无异常直接复用 c1，有异常才重算）
    - 距离指标同样分支处理，避免大 CTE 重复扫描
    """
    return r"""
SET statement_timeout = 0;
SET work_mem = '256MB';
SET max_parallel_workers_per_gather = 0;

-- ============================================================
-- Step 1: BS 中心点精算
-- 信号加权选种 + 设备去重 + 分箱中位数 + 异常剔除
-- ============================================================

-- 1.1 提取可信 LAC 范围内 GPS+RSRP 有效记录
DROP TABLE IF EXISTS rebuild2._tmp_bs_gps;
CREATE TABLE rebuild2._tmp_bs_gps AS
SELECT
    l."运营商编码"  AS op,
    l."标准制式"    AS tech,
    l."LAC"::text   AS lac,
    l."基站ID"      AS bs_id,
    l."CellID"      AS cell_id,
    l."设备标识"    AS dev,
    l."经度"        AS lon,
    l."纬度"        AS lat,
    l."RSRP"        AS rsrp
FROM rebuild2.l0_lac l
JOIN rebuild2.dim_lac_trusted t
    ON l."运营商编码" = t.operator_code
   AND l."标准制式"   = t.tech_norm
   AND l."LAC"        = t.lac::bigint
WHERE l."GPS有效" = true
  AND l."经度" BETWEEN 73 AND 135
  AND l."纬度" BETWEEN 3 AND 54
  AND l."RSRP" IS NOT NULL
  AND l."RSRP" < 0
  AND l."RSRP" NOT IN (-1, -110);

CREATE INDEX ON rebuild2._tmp_bs_gps(op, tech, lac, bs_id);
ANALYZE rebuild2._tmp_bs_gps;

-- 1.2 BS 级 GPS 点数统计
DROP TABLE IF EXISTS rebuild2._tmp_bs_cnt;
CREATE TABLE rebuild2._tmp_bs_cnt AS
SELECT op, tech, lac, bs_id,
    count(*)              AS n,
    count(DISTINCT dev)   AS n_dev,
    count(DISTINCT cell_id) AS n_cell
FROM rebuild2._tmp_bs_gps
GROUP BY op, tech, lac, bs_id;
CREATE UNIQUE INDEX ON rebuild2._tmp_bs_cnt(op, tech, lac, bs_id);
ANALYZE rebuild2._tmp_bs_cnt;

-- 1.3 设备去重 + 信号加权选种
DROP TABLE IF EXISTS rebuild2._tmp_bs_seeds;
CREATE TABLE rebuild2._tmp_bs_seeds AS
WITH
deduped AS (
    SELECT DISTINCT ON (g.op, g.tech, g.lac, g.bs_id, g.dev)
        g.op, g.tech, g.lac, g.bs_id, g.lon, g.lat, g.rsrp
    FROM rebuild2._tmp_bs_gps g
    JOIN rebuild2._tmp_bs_cnt c USING (op, tech, lac, bs_id)
    WHERE c.n > 100
    ORDER BY g.op, g.tech, g.lac, g.bs_id, g.dev, g.rsrp DESC
),
all_pts AS (
    SELECT op, tech, lac, bs_id, lon, lat, rsrp FROM deduped
    UNION ALL
    SELECT g.op, g.tech, g.lac, g.bs_id, g.lon, g.lat, g.rsrp
    FROM rebuild2._tmp_bs_gps g
    JOIN rebuild2._tmp_bs_cnt c USING (op, tech, lac, bs_id)
    WHERE c.n <= 100
),
ranked AS (
    SELECT *,
        ROW_NUMBER() OVER (PARTITION BY op, tech, lac, bs_id ORDER BY rsrp DESC) AS rn,
        COUNT(*)     OVER (PARTITION BY op, tech, lac, bs_id) AS grp
    FROM all_pts
)
SELECT op, tech, lac, bs_id, lon, lat, rsrp
FROM ranked
WHERE CASE
    WHEN grp >= 50 THEN rn <= 50
    WHEN grp >= 20 THEN rn <= 20
    WHEN grp >= 5  THEN rn <= GREATEST(CEIL(grp * 0.8)::int, 1)
    ELSE true
END;
CREATE INDEX ON rebuild2._tmp_bs_seeds(op, tech, lac, bs_id);
ANALYZE rebuild2._tmp_bs_seeds;

-- 1.4 第一轮中心点：分箱中位数（精度 ≈ 11m）
DROP TABLE IF EXISTS rebuild2._tmp_bs_c1;
CREATE TABLE rebuild2._tmp_bs_c1 AS
SELECT op, tech, lac, bs_id,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY round(lon * 10000)::int)
        / 10000.0 AS clon,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY round(lat * 10000)::int)
        / 10000.0 AS clat,
    count(*) AS n_seeds
FROM rebuild2._tmp_bs_seeds
GROUP BY op, tech, lac, bs_id;
CREATE UNIQUE INDEX ON rebuild2._tmp_bs_c1(op, tech, lac, bs_id);

-- 1.5a 物化种子到 c1 中心的距离（避免 CTE 重复扫描）
DROP TABLE IF EXISTS rebuild2._tmp_bs_seed_dist;
CREATE TABLE rebuild2._tmp_bs_seed_dist AS
SELECT s.op, s.tech, s.lac, s.bs_id, s.lon, s.lat,
    SQRT(
        POWER((s.lon - c.clon) * 85300, 2) +
        POWER((s.lat - c.clat) * 111000, 2)
    ) AS dist_m
FROM rebuild2._tmp_bs_seeds s
JOIN rebuild2._tmp_bs_c1 c USING (op, tech, lac, bs_id);
CREATE INDEX ON rebuild2._tmp_bs_seed_dist(op, tech, lac, bs_id);

-- 1.5b 标记有异常的 BS（max_dist > 2500m）
DROP TABLE IF EXISTS rebuild2._tmp_bs_outlier_flag;
CREATE TABLE rebuild2._tmp_bs_outlier_flag AS
SELECT op, tech, lac, bs_id,
    MAX(dist_m) AS max_dist_m,
    (MAX(dist_m) > 2500) AS has_outlier
FROM rebuild2._tmp_bs_seed_dist
GROUP BY op, tech, lac, bs_id;
CREATE UNIQUE INDEX ON rebuild2._tmp_bs_outlier_flag(op, tech, lac, bs_id);

-- 1.5c 组装 c2：无异常直接复制 c1，有异常剔除 >2500m 后重算
DROP TABLE IF EXISTS rebuild2._tmp_bs_c2;
CREATE TABLE rebuild2._tmp_bs_c2 AS
SELECT c.op, c.tech, c.lac, c.bs_id, c.clon, c.clat, c.n_seeds AS n_final, false AS had_outlier
FROM rebuild2._tmp_bs_c1 c
JOIN rebuild2._tmp_bs_outlier_flag f USING (op, tech, lac, bs_id)
WHERE NOT f.has_outlier
UNION ALL
SELECT sd.op, sd.tech, sd.lac, sd.bs_id,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY round(sd.lon * 10000)::int) / 10000.0 AS clon,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY round(sd.lat * 10000)::int) / 10000.0 AS clat,
    count(*) AS n_final,
    true AS had_outlier
FROM rebuild2._tmp_bs_seed_dist sd
JOIN rebuild2._tmp_bs_outlier_flag f USING (op, tech, lac, bs_id)
WHERE f.has_outlier AND sd.dist_m <= 2500
GROUP BY sd.op, sd.tech, sd.lac, sd.bs_id;
CREATE UNIQUE INDEX ON rebuild2._tmp_bs_c2(op, tech, lac, bs_id);

-- 1.6 距离指标（分支：无异常用已有距离，有异常重算到新中心）
DROP TABLE IF EXISTS rebuild2._tmp_bs_dist;
CREATE TABLE rebuild2._tmp_bs_dist AS
SELECT sd.op, sd.tech, sd.lac, sd.bs_id,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY sd.dist_m)::numeric, 1) AS p50_m,
    ROUND(PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY sd.dist_m)::numeric, 1) AS p90_m,
    ROUND(MAX(sd.dist_m)::numeric, 1) AS max_m
FROM rebuild2._tmp_bs_seed_dist sd
JOIN rebuild2._tmp_bs_outlier_flag f USING (op, tech, lac, bs_id)
WHERE NOT f.has_outlier
GROUP BY sd.op, sd.tech, sd.lac, sd.bs_id;

INSERT INTO rebuild2._tmp_bs_dist
SELECT sd.op, sd.tech, sd.lac, sd.bs_id,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY
        SQRT(POWER((sd.lon - c2.clon) * 85300, 2) + POWER((sd.lat - c2.clat) * 111000, 2))
    )::numeric, 1) AS p50_m,
    ROUND(PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY
        SQRT(POWER((sd.lon - c2.clon) * 85300, 2) + POWER((sd.lat - c2.clat) * 111000, 2))
    )::numeric, 1) AS p90_m,
    ROUND(MAX(
        SQRT(POWER((sd.lon - c2.clon) * 85300, 2) + POWER((sd.lat - c2.clat) * 111000, 2))
    )::numeric, 1) AS max_m
FROM rebuild2._tmp_bs_seed_dist sd
JOIN rebuild2._tmp_bs_outlier_flag f USING (op, tech, lac, bs_id)
JOIN rebuild2._tmp_bs_c2 c2 USING (op, tech, lac, bs_id)
WHERE f.has_outlier AND sd.dist_m <= 2500
GROUP BY sd.op, sd.tech, sd.lac, sd.bs_id;
CREATE UNIQUE INDEX ON rebuild2._tmp_bs_dist(op, tech, lac, bs_id);

-- 1.7 组装 dim_bs_refined
DROP TABLE IF EXISTS rebuild2.dim_bs_refined;
CREATE TABLE rebuild2.dim_bs_refined AS
SELECT
    b.operator_code, b.operator_cn, b.tech_norm, b.lac, b.bs_id,
    b.cell_count, b.record_count, b.distinct_device_count, b.max_active_days,
    b.first_seen, b.last_seen,
    c.clon                           AS gps_center_lon,
    c.clat                           AS gps_center_lat,
    c.n_final                        AS seed_count,
    COALESCE(c.had_outlier, false)   AS had_outlier_removal,
    COALESCE(cnt.n, 0)               AS total_gps_points,
    COALESCE(cnt.n_dev, 0)           AS distinct_gps_devices,
    COALESCE(cnt.n_cell, 0)          AS cells_with_gps,
    d.p50_m                          AS gps_p50_dist_m,
    d.p90_m                          AS gps_p90_dist_m,
    d.max_m                          AS gps_max_dist_m,
    CASE
        WHEN COALESCE(cnt.n_cell, 0) >= 2 THEN 'Usable'
        WHEN COALESCE(cnt.n_cell, 0) = 1  THEN 'Risk'
        ELSE 'Unusable'
    END                              AS gps_quality,
    b.gps_center_lon                 AS old_center_lon,
    b.gps_center_lat                 AS old_center_lat,
    b.valid_gps_count                AS old_valid_gps_count,
    now()                            AS created_at
FROM rebuild2.dim_bs_stats b
LEFT JOIN rebuild2._tmp_bs_cnt  cnt ON b.operator_code = cnt.op  AND b.tech_norm = cnt.tech AND b.lac = cnt.lac AND b.bs_id = cnt.bs_id
LEFT JOIN rebuild2._tmp_bs_c2   c   ON b.operator_code = c.op    AND b.tech_norm = c.tech   AND b.lac = c.lac   AND b.bs_id = c.bs_id
LEFT JOIN rebuild2._tmp_bs_dist d   ON b.operator_code = d.op    AND b.tech_norm = d.tech   AND b.lac = d.lac   AND b.bs_id = d.bs_id
ORDER BY b.record_count DESC;

CREATE INDEX ON rebuild2.dim_bs_refined(operator_code, tech_norm, lac, bs_id);
CREATE INDEX ON rebuild2.dim_bs_refined(gps_quality);

-- 清理临时表
DROP TABLE IF EXISTS rebuild2._tmp_bs_gps;
DROP TABLE IF EXISTS rebuild2._tmp_bs_cnt;
DROP TABLE IF EXISTS rebuild2._tmp_bs_seeds;
DROP TABLE IF EXISTS rebuild2._tmp_bs_c1;
DROP TABLE IF EXISTS rebuild2._tmp_bs_seed_dist;
DROP TABLE IF EXISTS rebuild2._tmp_bs_outlier_flag;
DROP TABLE IF EXISTS rebuild2._tmp_bs_c2;
DROP TABLE IF EXISTS rebuild2._tmp_bs_dist;

-- 元数据记录
CREATE TABLE IF NOT EXISTS rebuild2_meta.enrich_result (
    id         SERIAL PRIMARY KEY,
    step_code  TEXT NOT NULL,
    run_label  TEXT DEFAULT 'default',
    stat_key   TEXT NOT NULL,
    stat_value JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);

INSERT INTO rebuild2_meta.enrich_result (step_code, stat_key, stat_value)
SELECT 'step1_bs_refined', 'summary',
    jsonb_build_object(
        'total_bs',  count(*),
        'usable',    count(*) FILTER (WHERE gps_quality = 'Usable'),
        'risk',      count(*) FILTER (WHERE gps_quality = 'Risk'),
        'unusable',  count(*) FILTER (WHERE gps_quality = 'Unusable'),
        'has_center', count(*) FILTER (WHERE gps_center_lon IS NOT NULL),
        'outlier_removed', count(*) FILTER (WHERE had_outlier_removal)
    )
FROM rebuild2.dim_bs_refined;

SELECT 'Step 1 完成: dim_bs_refined 已创建' AS status;
"""


# ═══════════════════════════════════════════════════════════
#  Step 2：Cell GPS 校验（dim_cell_refined）
# ═══════════════════════════════════════════════════════════

STEP2_PARAMS = {
    "anomaly_threshold_4g_m": 2000,
    "anomaly_threshold_5g_m": 1000,
    "gps_bounds": "经度 73~135, 纬度 3~54（中国范围）",
    "cell_center_method": "PERCENTILE_CONT 分箱中位数（无信号加权，精度 ≈ 11m）",
    "distance_formula": "欧氏近似：1°lon ≈ 85300m, 1°lat ≈ 111000m",
    "anomaly_reason": "cell center 到 BS center 距离超阈值（4G>2000m / 5G>1000m）",
}


@router.get("/step2/preview")
async def step2_preview(db: AsyncSession = Depends(get_db)):
    """Step 2 预览：dim_cell_stats 总览 + 算法参数。"""

    # 依赖检查
    bs_check = await db.execute(text(_table_exists_sql("dim_bs_refined")))
    if not dict(bs_check.mappings().first())["ok"]:
        return {"ready": False, "error": "请先完成 Step 1（dim_bs_refined 尚未就绪）"}

    # dim_cell_stats 总览
    overview_result = await db.execute(text("""
        SELECT
            count(*)                                              AS total_cells,
            count(DISTINCT (operator_code, tech_norm, lac, bs_id)) AS total_bs,
            count(*) FILTER (WHERE gps_center_lon IS NOT NULL)   AS cells_with_gps,
            count(*) FILTER (WHERE gps_center_lon IS NULL)       AS cells_no_gps,
            sum(valid_gps_count)::bigint                         AS total_gps_points,
            sum(record_count)::bigint                            AS total_records
        FROM rebuild2.dim_cell_stats
    """))
    overview = dict(overview_result.mappings().first())

    # 按技术制式分组
    by_tech_result = await db.execute(text("""
        SELECT tech_norm,
            count(*)                                            AS cell_count,
            count(*) FILTER (WHERE gps_center_lon IS NOT NULL) AS with_gps,
            sum(valid_gps_count)::bigint                       AS gps_points
        FROM rebuild2.dim_cell_stats
        GROUP BY tech_norm
        ORDER BY cell_count DESC
    """))
    by_tech = [dict(r) for r in by_tech_result.mappings().all()]

    # 预估异常数量（根据 dim_cell_stats + dim_bs_refined 粗估）
    anomaly_est_result = await db.execute(text("""
        SELECT
            count(*) FILTER (WHERE
                cs.gps_center_lon IS NOT NULL AND br.gps_center_lon IS NOT NULL AND
                SQRT(POWER((cs.gps_center_lon - br.gps_center_lon) * 85300, 2) +
                     POWER((cs.gps_center_lat - br.gps_center_lat) * 111000, 2)) >
                CASE WHEN cs.tech_norm LIKE '%5G%' THEN 1000 ELSE 2000 END
            ) AS estimated_anomalies,
            count(*) FILTER (WHERE cs.gps_center_lon IS NOT NULL AND br.gps_center_lon IS NOT NULL) AS comparable
        FROM rebuild2.dim_cell_stats cs
        LEFT JOIN rebuild2.dim_bs_refined br
            ON cs.operator_code = br.operator_code
           AND cs.tech_norm     = br.tech_norm
           AND cs.lac           = br.lac
           AND cs.bs_id         = br.bs_id
    """))
    anomaly_est = dict(anomaly_est_result.mappings().first())

    return {
        "ready": True,
        "params": STEP2_PARAMS,
        "overview": overview,
        "by_tech": by_tech,
        "anomaly_estimate": anomaly_est,
    }


@router.post("/step2/execute")
async def step2_execute():
    """启动 Step 2 Cell GPS 校验（后台 SSH psql 执行）。"""
    task_key = "step2"
    if task_key in _tasks and not _tasks[task_key].done():
        return {"ok": False, "error": "Step 2 正在执行中，请等待完成"}

    sql = _build_step2_sql()

    async def run():
        result = await _ssh_psql(sql)
        _task_results[task_key] = result
        return result

    _tasks[task_key] = asyncio.create_task(run())
    return {"ok": True, "message": "Step 2 已启动，请轮询 /step2/status 查看进度"}


@router.get("/step2/status")
async def step2_status(db: AsyncSession = Depends(get_db)):
    """检查 Step 2 执行状态。"""
    task_key = "step2"
    task = _tasks.get(task_key)

    if task and not task.done():
        return {"status": "running", "message": "Cell GPS 校验执行中..."}

    if task and task.done():
        try:
            result = task.result()
        except Exception as e:
            return {"status": "error", "message": str(e)}
        if result["returncode"] != 0:
            return {
                "status": "error",
                "message": "SQL 执行失败",
                "stderr": result["stderr"],
                "stdout": result["stdout"],
            }

    check = await db.execute(text(_table_exists_sql("dim_cell_refined")))
    exists = dict(check.mappings().first())["ok"]
    if not exists:
        return {"status": "not_started", "message": "dim_cell_refined 尚未创建"}

    return {"status": "done", "message": "dim_cell_refined 已就绪"}


@router.get("/step2/result")
async def step2_result(db: AsyncSession = Depends(get_db)):
    """读取 dim_cell_refined 结果。"""
    check = await db.execute(text(_table_exists_sql("dim_cell_refined")))
    if not dict(check.mappings().first())["ok"]:
        return {"exists": False}

    # 总览
    total_result = await db.execute(text("""
        SELECT
            count(*)                                                  AS total_cells,
            count(*) FILTER (WHERE gps_center_lon IS NOT NULL)       AS cells_with_gps,
            count(*) FILTER (WHERE gps_count > 0)                    AS cells_with_raw_gps,
            count(*) FILTER (WHERE gps_anomaly = true)               AS anomaly_cells,
            count(*) FILTER (WHERE gps_anomaly = false
                AND gps_center_lon IS NOT NULL)                       AS normal_cells,
            ROUND(AVG(dist_to_bs_m) FILTER (WHERE dist_to_bs_m IS NOT NULL)::numeric, 0) AS avg_dist_to_bs_m
        FROM rebuild2.dim_cell_refined
    """))
    totals = dict(total_result.mappings().first())

    # 按技术制式
    by_tech_result = await db.execute(text("""
        SELECT tech_norm,
            count(*)                                             AS cell_count,
            count(*) FILTER (WHERE gps_center_lon IS NOT NULL)  AS with_gps,
            count(*) FILTER (WHERE gps_anomaly = true)          AS anomaly_count,
            ROUND(AVG(dist_to_bs_m)
                  FILTER (WHERE dist_to_bs_m IS NOT NULL)::numeric, 0) AS avg_dist_m
        FROM rebuild2.dim_cell_refined
        GROUP BY tech_norm
        ORDER BY cell_count DESC
    """))
    by_tech = [dict(r) for r in by_tech_result.mappings().all()]

    # BS GPS 质量分布
    bs_quality_result = await db.execute(text("""
        SELECT bs_gps_quality,
            count(*)                                            AS cell_count,
            count(*) FILTER (WHERE gps_anomaly = true)         AS anomaly_count
        FROM rebuild2.dim_cell_refined
        GROUP BY bs_gps_quality
        ORDER BY cell_count DESC
    """))
    bs_quality = [dict(r) for r in bs_quality_result.mappings().all()]

    # 异常原因分布
    anomaly_result = await db.execute(text("""
        SELECT gps_anomaly_reason, count(*) AS cnt
        FROM rebuild2.dim_cell_refined
        WHERE gps_anomaly = true
        GROUP BY gps_anomaly_reason
        ORDER BY cnt DESC
    """))
    anomaly_reasons = [dict(r) for r in anomaly_result.mappings().all()]

    # Top 20 异常 Cell
    top_anomaly_result = await db.execute(text("""
        SELECT operator_cn, tech_norm, lac, cell_id, bs_id, sector_id,
            gps_center_lon, gps_center_lat, dist_to_bs_m, gps_anomaly_reason,
            bs_gps_quality, record_count
        FROM rebuild2.dim_cell_refined
        WHERE gps_anomaly = true
        ORDER BY dist_to_bs_m DESC NULLS LAST
        LIMIT 20
    """))
    top_anomalies = [dict(r) for r in top_anomaly_result.mappings().all()]

    return {
        "exists": True,
        "totals": totals,
        "by_tech": by_tech,
        "bs_quality": bs_quality,
        "anomaly_reasons": anomaly_reasons,
        "top_anomalies": top_anomalies,
    }


# ─── Step 2 SQL 生成 ──────────────────────────────────────

def _build_step2_sql() -> str:
    """生成 Step 2 Cell GPS 校验的完整 SQL 脚本。"""
    return r"""
SET statement_timeout = 0;
SET work_mem = '256MB';
SET max_parallel_workers_per_gather = 0;

-- ============================================================
-- Step 2: Cell GPS 校验（dim_cell_refined）
-- 提取 Cell GPS 中心点，与 BS 中心比较，标记异常
-- ============================================================

-- 2.1 提取可信 LAC 范围内的 GPS 有效记录（Cell 粒度）
DROP TABLE IF EXISTS rebuild2._tmp_cell_gps;
CREATE TABLE rebuild2._tmp_cell_gps AS
SELECT
    l."运营商编码"  AS op,
    l."标准制式"    AS tech,
    l."LAC"::text   AS lac,
    l."CellID"      AS cell_id,
    l."基站ID"      AS bs_id,
    l."设备标识"    AS dev,
    l."经度"        AS lon,
    l."纬度"        AS lat
FROM rebuild2.l0_lac l
JOIN rebuild2.dim_lac_trusted t
    ON l."运营商编码" = t.operator_code
   AND l."标准制式"   = t.tech_norm
   AND l."LAC"        = t.lac::bigint
WHERE l."GPS有效" = true
  AND l."经度" BETWEEN 73 AND 135
  AND l."纬度" BETWEEN 3 AND 54;

CREATE INDEX ON rebuild2._tmp_cell_gps(op, tech, lac, cell_id);
ANALYZE rebuild2._tmp_cell_gps;

-- 2.2 计算 Cell GPS 中心点（分箱中位数，无信号加权）
DROP TABLE IF EXISTS rebuild2._tmp_cell_center;
CREATE TABLE rebuild2._tmp_cell_center AS
SELECT
    op, tech, lac, cell_id,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY round(lon * 10000)::int)
        / 10000.0 AS clon,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY round(lat * 10000)::int)
        / 10000.0 AS clat,
    count(*)              AS gps_count,
    count(DISTINCT dev)   AS gps_device_count
FROM rebuild2._tmp_cell_gps
GROUP BY op, tech, lac, cell_id;

CREATE UNIQUE INDEX ON rebuild2._tmp_cell_center(op, tech, lac, cell_id);
ANALYZE rebuild2._tmp_cell_center;

-- 2.3 计算 Cell 中心到 BS 中心的距离，并标记异常
DROP TABLE IF EXISTS rebuild2._tmp_cell_dist;
CREATE TABLE rebuild2._tmp_cell_dist AS
SELECT
    cc.op, cc.tech, cc.lac, cc.cell_id,
    cc.clon, cc.clat, cc.gps_count, cc.gps_device_count,
    br.gps_center_lon  AS bs_lon,
    br.gps_center_lat  AS bs_lat,
    br.gps_quality     AS bs_gps_quality,
    CASE
        WHEN br.gps_center_lon IS NOT NULL THEN
            ROUND(SQRT(
                POWER((cc.clon - br.gps_center_lon) * 85300, 2) +
                POWER((cc.clat - br.gps_center_lat) * 111000, 2)
            )::numeric, 1)
        ELSE NULL
    END AS dist_to_bs_m,
    CASE
        WHEN br.gps_center_lon IS NULL THEN false
        WHEN cc.tech LIKE '%5G%' AND
            SQRT(POWER((cc.clon - br.gps_center_lon) * 85300, 2) +
                 POWER((cc.clat - br.gps_center_lat) * 111000, 2)) > 1000 THEN true
        WHEN cc.tech NOT LIKE '%5G%' AND
            SQRT(POWER((cc.clon - br.gps_center_lon) * 85300, 2) +
                 POWER((cc.clat - br.gps_center_lat) * 111000, 2)) > 2000 THEN true
        ELSE false
    END AS gps_anomaly,
    CASE
        WHEN br.gps_center_lon IS NULL THEN NULL
        WHEN cc.tech LIKE '%5G%' AND
            SQRT(POWER((cc.clon - br.gps_center_lon) * 85300, 2) +
                 POWER((cc.clat - br.gps_center_lat) * 111000, 2)) > 1000
            THEN 'cell_to_bs_dist>1000m(5G)'
        WHEN cc.tech NOT LIKE '%5G%' AND
            SQRT(POWER((cc.clon - br.gps_center_lon) * 85300, 2) +
                 POWER((cc.clat - br.gps_center_lat) * 111000, 2)) > 2000
            THEN 'cell_to_bs_dist>2000m(non5G)'
        ELSE NULL
    END AS gps_anomaly_reason
FROM rebuild2._tmp_cell_center cc
LEFT JOIN rebuild2.dim_bs_refined br
    ON cc.op   = br.operator_code
   AND cc.tech = br.tech_norm
   AND cc.lac  = br.lac
   AND (SELECT bs_id FROM rebuild2.dim_cell_stats
        WHERE operator_code = cc.op AND tech_norm = cc.tech
          AND lac = cc.lac AND cell_id = cc.cell_id LIMIT 1)
       = br.bs_id;

CREATE UNIQUE INDEX ON rebuild2._tmp_cell_dist(op, tech, lac, cell_id);
ANALYZE rebuild2._tmp_cell_dist;

-- 2.4 组装 dim_cell_refined（join dim_cell_stats 获取完整字段）
DROP TABLE IF EXISTS rebuild2.dim_cell_refined;
CREATE TABLE rebuild2.dim_cell_refined AS
SELECT
    cs.operator_code,
    cs.operator_cn,
    cs.tech_norm,
    cs.lac,
    cs.cell_id,
    cs.bs_id,
    cs.sector_id,
    cs.record_count,
    cs.distinct_device_count,
    cs.active_days,
    COALESCE(cd.clon, cs.gps_center_lon)     AS gps_center_lon,
    COALESCE(cd.clat, cs.gps_center_lat)     AS gps_center_lat,
    COALESCE(cd.gps_count, cs.valid_gps_count) AS gps_count,
    COALESCE(cd.gps_device_count, 0)         AS gps_device_count,
    cd.dist_to_bs_m,
    COALESCE(cd.gps_anomaly, false)          AS gps_anomaly,
    cd.gps_anomaly_reason,
    COALESCE(cd.bs_gps_quality,
        (SELECT gps_quality FROM rebuild2.dim_bs_refined br
         WHERE br.operator_code = cs.operator_code
           AND br.tech_norm     = cs.tech_norm
           AND br.lac           = cs.lac
           AND br.bs_id         = cs.bs_id LIMIT 1)
    )                                        AS bs_gps_quality,
    now()                                    AS created_at
FROM rebuild2.dim_cell_stats cs
LEFT JOIN rebuild2._tmp_cell_dist cd
    ON cs.operator_code = cd.op
   AND cs.tech_norm     = cd.tech
   AND cs.lac           = cd.lac
   AND cs.cell_id       = cd.cell_id
ORDER BY cs.record_count DESC;

CREATE INDEX ON rebuild2.dim_cell_refined(operator_code, tech_norm, lac, cell_id);
CREATE INDEX ON rebuild2.dim_cell_refined(operator_code, tech_norm, lac, bs_id);
CREATE INDEX ON rebuild2.dim_cell_refined(gps_anomaly);
CREATE INDEX ON rebuild2.dim_cell_refined(bs_gps_quality);

-- 清理临时表
DROP TABLE IF EXISTS rebuild2._tmp_cell_gps;
DROP TABLE IF EXISTS rebuild2._tmp_cell_center;
DROP TABLE IF EXISTS rebuild2._tmp_cell_dist;

SELECT 'Step 2 完成: dim_cell_refined 已创建' AS status;
"""


# ═══════════════════════════════════════════════════════════
#  Step 3：明细 GPS 修正（_tmp_gps_fixed）
# ═══════════════════════════════════════════════════════════

STEP3_PARAMS = {
    "original_keep_threshold_4g_m": 1000,
    "original_keep_threshold_5g_m": 500,
    "gps_sources": {
        "original":        "原始 GPS 有效且到 Cell 中心距离 ≤ 阈值",
        "cell_center":     "原始 GPS 超阈值或无 GPS，用 Cell 中心填充",
        "bs_center":       "Cell 无 GPS，BS 质量 Usable，用 BS 中心填充",
        "bs_center_risk":  "Cell 无 GPS，BS 质量 Risk，用 BS 中心填充（风险标记）",
        "not_filled":      "Cell 无 GPS 且 BS 质量 Unusable，不填充",
    },
    "note": "处理约 3000 万条记录，使用 CREATE TABLE AS 模式避免大 CTE",
}


@router.get("/step3/preview")
async def step3_preview(db: AsyncSession = Depends(get_db)):
    """Step 3 预览：GPS 来源预估 + 算法参数。"""

    cell_check = await db.execute(text(_table_exists_sql("dim_cell_refined")))
    if not dict(cell_check.mappings().first())["ok"]:
        return {"ready": False, "error": "请先完成 Step 2（dim_cell_refined 尚未就绪）"}

    # 可信 LAC 范围内记录总数
    total_result = await db.execute(text("""
        SELECT count(*) AS trusted_records
        FROM rebuild2.l0_lac l
        JOIN rebuild2.dim_lac_trusted t
            ON l."运营商编码" = t.operator_code
           AND l."标准制式"   = t.tech_norm
           AND l."LAC"        = t.lac::bigint
    """))
    total = dict(total_result.mappings().first())

    # GPS 来源预估（基于 dim_cell_refined）
    source_est_result = await db.execute(text("""
        SELECT
            count(*) FILTER (WHERE gps_center_lon IS NOT NULL
                AND NOT gps_anomaly) AS cells_usable_gps,
            count(*) FILTER (WHERE gps_center_lon IS NOT NULL
                AND gps_anomaly)     AS cells_anomaly_gps,
            count(*) FILTER (WHERE gps_center_lon IS NULL
                AND bs_gps_quality = 'Usable')  AS cells_bs_usable,
            count(*) FILTER (WHERE gps_center_lon IS NULL
                AND bs_gps_quality = 'Risk')     AS cells_bs_risk,
            count(*) FILTER (WHERE gps_center_lon IS NULL
                AND bs_gps_quality = 'Unusable') AS cells_bs_unusable,
            count(*) FILTER (WHERE gps_center_lon IS NULL
                AND bs_gps_quality IS NULL)       AS cells_no_bs
        FROM rebuild2.dim_cell_refined
    """))
    source_est = dict(source_est_result.mappings().first())

    # 当前 GPS 有效率
    gps_ratio_result = await db.execute(text("""
        SELECT
            count(*) AS total,
            count(*) FILTER (WHERE "GPS有效" = true
                AND "经度" BETWEEN 73 AND 135
                AND "纬度" BETWEEN 3 AND 54) AS gps_valid
        FROM rebuild2.l0_lac l
        JOIN rebuild2.dim_lac_trusted t
            ON l."运营商编码" = t.operator_code
           AND l."标准制式"   = t.tech_norm
           AND l."LAC"        = t.lac::bigint
    """))
    gps_ratio = dict(gps_ratio_result.mappings().first())

    return {
        "ready": True,
        "params": STEP3_PARAMS,
        "record_count": total,
        "cell_gps_source_estimate": source_est,
        "current_gps_ratio": gps_ratio,
    }


@router.post("/step3/execute")
async def step3_execute():
    """启动 Step 3 明细 GPS 修正（后台 SSH psql 执行）。"""
    task_key = "step3"
    if task_key in _tasks and not _tasks[task_key].done():
        return {"ok": False, "error": "Step 3 正在执行中，请等待完成"}

    sql = _build_step3_sql()

    async def run():
        result = await _ssh_psql(sql)
        _task_results[task_key] = result
        return result

    _tasks[task_key] = asyncio.create_task(run())
    return {"ok": True, "message": "Step 3 已启动，请轮询 /step3/status 查看进度"}


@router.get("/step3/status")
async def step3_status(db: AsyncSession = Depends(get_db)):
    """检查 Step 3 执行状态。"""
    task_key = "step3"
    task = _tasks.get(task_key)

    if task and not task.done():
        return {"status": "running", "message": "明细 GPS 修正执行中（30M+ 行，耗时较长）..."}

    if task and task.done():
        try:
            result = task.result()
        except Exception as e:
            return {"status": "error", "message": str(e)}
        if result["returncode"] != 0:
            return {
                "status": "error",
                "message": "SQL 执行失败",
                "stderr": result["stderr"],
                "stdout": result["stdout"],
            }

    # _tmp_gps_fixed 可能已被 Step 5 清理，数据在 dwd_fact_enriched 中
    for tbl in ("_tmp_gps_fixed", "dwd_fact_enriched"):
        check = await db.execute(text(_table_exists_sql(tbl)))
        if dict(check.mappings().first())["ok"]:
            # 确认表中有 gps_source 列
            col_check = await db.execute(text(f"""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'rebuild2' AND table_name = '{tbl}'
                    AND column_name = 'gps_source'
                ) AS ok
            """))
            if dict(col_check.mappings().first())["ok"]:
                return {"status": "done", "message": f"GPS 修正已完成（数据在 {tbl}）"}

    return {"status": "not_started", "message": "GPS 修正尚未执行"}


@router.get("/step3/result")
async def step3_result(db: AsyncSession = Depends(get_db)):
    """读取 Step 3 GPS 修正统计（从预聚合元数据读取，避免扫描 3000 万行）。"""
    # 优先从元数据读取
    meta = await db.execute(text("""
        SELECT stat_value FROM rebuild2_meta.enrich_result
        WHERE step_code = 'step3_gps_fixed' AND stat_key = 'summary'
        ORDER BY created_at DESC LIMIT 1
    """))
    row = meta.mappings().first()
    if row:
        v = row["stat_value"]
        source_dist = v.get("source_distribution", [])
        total_rows = v.get("total_rows", 0)
        rows_with_gps = v.get("rows_with_gps", 0)
        rows_no_gps = v.get("rows_no_gps", 0)
        return {
            "exists": True,
            "totals": {
                "total_rows": total_rows,
                "rows_with_gps": rows_with_gps,
                "rows_no_gps": rows_no_gps,
                "gps_coverage_pct": round(rows_with_gps / total_rows * 100, 2) if total_rows else 0,
                "data_table": "dwd_fact_enriched",
            },
            "source_distribution": source_dist,
        }

    # 回退：检查表是否存在
    for tbl in ("dwd_fact_enriched", "_tmp_gps_fixed"):
        check = await db.execute(text(_table_exists_sql(tbl)))
        if dict(check.mappings().first())["ok"]:
            return {"exists": True, "totals": {"data_table": tbl}, "source_distribution": [],
                    "_note": "元数据缺失，请重新执行 Step 3 以生成统计"}

    return {"exists": False}


# ─── Step 3 SQL 生成 ──────────────────────────────────────

def _build_step3_sql() -> str:
    """生成 Step 3 明细 GPS 修正的完整 SQL 脚本。"""
    return r"""
SET statement_timeout = 0;
SET work_mem = '256MB';
SET max_parallel_workers_per_gather = 0;

-- ============================================================
-- Step 3: 明细 GPS 修正（_tmp_gps_fixed）
-- 对 30M+ 条可信 LAC 范围内记录，逐行判断 GPS 来源
-- ============================================================

-- 3.1 先物化可信 LAC 范围内的全量行（含行号供后续关联）
DROP TABLE IF EXISTS rebuild2._tmp_l0_trusted;
CREATE TABLE rebuild2._tmp_l0_trusted AS
SELECT
    l.ctid                          AS l0_row_id,
    l."运营商编码"                   AS op,
    l."标准制式"                     AS tech,
    l."LAC"::text                   AS lac,
    l."CellID"                      AS cell_id,
    l."基站ID"                      AS bs_id,
    l."GPS有效"                      AS gps_valid,
    l."经度"                         AS raw_lon,
    l."纬度"                         AS raw_lat,
    l."上报时间"                     AS report_time,
    l."设备标识"                     AS dev_id,
    l."RSRP"                        AS rsrp,
    l."RSRQ"                        AS rsrq,
    l."SINR"                        AS sinr,
    l."Dbm"                         AS dbm
FROM rebuild2.l0_lac l
JOIN rebuild2.dim_lac_trusted t
    ON l."运营商编码" = t.operator_code
   AND l."标准制式"   = t.tech_norm
   AND l."LAC"        = t.lac::bigint;

CREATE INDEX ON rebuild2._tmp_l0_trusted(op, tech, lac, cell_id);
CREATE INDEX ON rebuild2._tmp_l0_trusted(dev_id);
ANALYZE rebuild2._tmp_l0_trusted;

-- 3.2 Cell GPS 字典（仅取非异常 Cell 的有效中心，异常 Cell 视为无 GPS）
DROP TABLE IF EXISTS rebuild2._tmp_cell_gps_dict;
CREATE TABLE rebuild2._tmp_cell_gps_dict AS
SELECT
    operator_code  AS op,
    tech_norm      AS tech,
    lac,
    cell_id,
    bs_id,
    gps_center_lon AS cell_lon,
    gps_center_lat AS cell_lat,
    gps_anomaly,
    bs_gps_quality
FROM rebuild2.dim_cell_refined;

CREATE UNIQUE INDEX ON rebuild2._tmp_cell_gps_dict(op, tech, lac, cell_id);
ANALYZE rebuild2._tmp_cell_gps_dict;

-- 3.3 BS GPS 字典
DROP TABLE IF EXISTS rebuild2._tmp_bs_gps_dict;
CREATE TABLE rebuild2._tmp_bs_gps_dict AS
SELECT
    operator_code  AS op,
    tech_norm      AS tech,
    lac,
    bs_id,
    gps_center_lon AS bs_lon,
    gps_center_lat AS bs_lat,
    gps_quality
FROM rebuild2.dim_bs_refined;

CREATE UNIQUE INDEX ON rebuild2._tmp_bs_gps_dict(op, tech, lac, bs_id);
ANALYZE rebuild2._tmp_bs_gps_dict;

-- 3.4 组装 GPS 修正结果
DROP TABLE IF EXISTS rebuild2._tmp_gps_fixed;
CREATE TABLE rebuild2._tmp_gps_fixed AS
SELECT
    l.l0_row_id,
    l.op,
    l.tech,
    l.lac,
    l.cell_id,
    l.bs_id,
    -- 最终经纬度
    CASE
        -- 原始 GPS 有效且到 Cell 中心距离 ≤ 阈值 → 保留原始
        WHEN l.gps_valid = true
             AND l.raw_lon BETWEEN 73 AND 135
             AND l.raw_lat BETWEEN 3 AND 54
             AND c.cell_lon IS NOT NULL
             AND NOT COALESCE(c.gps_anomaly, false)
             AND SQRT(POWER((l.raw_lon - c.cell_lon) * 85300, 2) +
                      POWER((l.raw_lat - c.cell_lat) * 111000, 2))
                 <= CASE WHEN l.tech LIKE '%5G%' THEN 500 ELSE 1000 END
            THEN l.raw_lon
        -- 原始 GPS 超阈值或无 GPS，Cell 有有效中心 → Cell 中心
        WHEN c.cell_lon IS NOT NULL AND NOT COALESCE(c.gps_anomaly, false)
            THEN c.cell_lon
        -- Cell 无有效 GPS，BS Usable → BS 中心
        WHEN (c.cell_lon IS NULL OR COALESCE(c.gps_anomaly, false))
             AND b.bs_lon IS NOT NULL
             AND b.gps_quality IN ('Usable', 'Risk')
            THEN b.bs_lon
        ELSE NULL
    END AS lon_final,
    CASE
        WHEN l.gps_valid = true
             AND l.raw_lon BETWEEN 73 AND 135
             AND l.raw_lat BETWEEN 3 AND 54
             AND c.cell_lon IS NOT NULL
             AND NOT COALESCE(c.gps_anomaly, false)
             AND SQRT(POWER((l.raw_lon - c.cell_lon) * 85300, 2) +
                      POWER((l.raw_lat - c.cell_lat) * 111000, 2))
                 <= CASE WHEN l.tech LIKE '%5G%' THEN 500 ELSE 1000 END
            THEN l.raw_lat
        WHEN c.cell_lon IS NOT NULL AND NOT COALESCE(c.gps_anomaly, false)
            THEN c.cell_lat
        WHEN (c.cell_lon IS NULL OR COALESCE(c.gps_anomaly, false))
             AND b.bs_lon IS NOT NULL
             AND b.gps_quality IN ('Usable', 'Risk')
            THEN b.bs_lat
        ELSE NULL
    END AS lat_final,
    -- GPS 来源标记
    CASE
        WHEN l.gps_valid = true
             AND l.raw_lon BETWEEN 73 AND 135
             AND l.raw_lat BETWEEN 3 AND 54
             AND c.cell_lon IS NOT NULL
             AND NOT COALESCE(c.gps_anomaly, false)
             AND SQRT(POWER((l.raw_lon - c.cell_lon) * 85300, 2) +
                      POWER((l.raw_lat - c.cell_lat) * 111000, 2))
                 <= CASE WHEN l.tech LIKE '%5G%' THEN 500 ELSE 1000 END
            THEN 'original'
        WHEN c.cell_lon IS NOT NULL AND NOT COALESCE(c.gps_anomaly, false)
            THEN 'cell_center'
        WHEN (c.cell_lon IS NULL OR COALESCE(c.gps_anomaly, false))
             AND b.bs_lon IS NOT NULL AND b.gps_quality = 'Usable'
            THEN 'bs_center'
        WHEN (c.cell_lon IS NULL OR COALESCE(c.gps_anomaly, false))
             AND b.bs_lon IS NOT NULL AND b.gps_quality = 'Risk'
            THEN 'bs_center_risk'
        ELSE 'not_filled'
    END AS gps_source,
    l.report_time  AS "上报时间",
    l.dev_id       AS "设备标识",
    l.rsrp         AS "RSRP",
    l.rsrq         AS "RSRQ",
    l.sinr         AS "SINR",
    l.dbm          AS "Dbm"
FROM rebuild2._tmp_l0_trusted l
LEFT JOIN rebuild2._tmp_cell_gps_dict c
    ON l.op      = c.op
   AND l.tech    = c.tech
   AND l.lac     = c.lac
   AND l.cell_id = c.cell_id
LEFT JOIN rebuild2._tmp_bs_gps_dict b
    ON l.op   = b.op
   AND l.tech = b.tech
   AND l.lac  = b.lac
   AND l.bs_id = b.bs_id;

CREATE INDEX ON rebuild2._tmp_gps_fixed(op, tech, lac, cell_id);
CREATE INDEX ON rebuild2._tmp_gps_fixed(op, tech, lac, bs_id);
CREATE INDEX ON rebuild2._tmp_gps_fixed(gps_source);
CREATE INDEX ON rebuild2._tmp_gps_fixed("设备标识");
CREATE INDEX ON rebuild2._tmp_gps_fixed("上报时间");
ANALYZE rebuild2._tmp_gps_fixed;

-- 清理中间字典表（保留 _tmp_gps_fixed 供 Step 4 使用）
DROP TABLE IF EXISTS rebuild2._tmp_l0_trusted;
DROP TABLE IF EXISTS rebuild2._tmp_cell_gps_dict;
DROP TABLE IF EXISTS rebuild2._tmp_bs_gps_dict;

SELECT 'Step 3 完成: _tmp_gps_fixed 已创建' AS status;
"""


# ═══════════════════════════════════════════════════════════
#  Step 4：信号补齐（dwd_fact_enriched）
# ═══════════════════════════════════════════════════════════

STEP4_PARAMS = {
    "stage1": "同 Cell 最近时间记录补齐：LAG/LEAD 窗口函数",
    "stage2": "同 BS 回退补齐：Cell 无信号时，用同 BS 内记录最多 Cell 的最近记录",
    "signal_fields": ["RSRP", "RSRQ", "SINR", "Dbm"],
    "fill_source_values": {
        "original":    "原始记录有信号值",
        "cell_fill":   "Stage 1 补齐（同 Cell 最近邻）",
        "bs_fill":     "Stage 2 补齐（同 BS 主要 Cell 最近邻）",
        "unfilled":    "无法补齐",
    },
}


@router.get("/step4/preview")
async def step4_preview(db: AsyncSession = Depends(get_db)):
    """Step 4 预览：信号缺失情况 + 补齐策略说明。"""

    # 检查 Step 3 是否完成（数据可能在 _tmp_gps_fixed 或 dwd_fact_enriched）
    step3_done = False
    for tbl in ("_tmp_gps_fixed", "dwd_fact_enriched"):
        chk = await db.execute(text(_table_exists_sql(tbl)))
        if dict(chk.mappings().first())["ok"]:
            step3_done = True
            break
    if not step3_done:
        return {"ready": False, "error": "请先完成第三步（GPS 修正尚未执行）"}

    # 使用 Phase 2 已知的覆盖率数据（避免扫描 3000 万行大表）
    signal_stats = {
        "total_rows": 30082381,
        "rsrp_valid_pct": 88.9,
        "rsrq_missing_pct": 19.5,
        "sinr_missing_pct": 43.0,
        "dbm_missing_pct": 42.1,
    }

    return {
        "ready": True,
        "params": STEP4_PARAMS,
        "signal_coverage": signal_stats,
    }


@router.post("/step4/execute")
async def step4_execute():
    """启动 Step 4 信号补齐（后台 SSH psql 执行）。"""
    task_key = "step4"
    if task_key in _tasks and not _tasks[task_key].done():
        return {"ok": False, "error": "Step 4 正在执行中，请等待完成"}

    sql = _build_step4_sql()

    async def run():
        result = await _ssh_psql(sql)
        _task_results[task_key] = result
        return result

    _tasks[task_key] = asyncio.create_task(run())
    return {"ok": True, "message": "Step 4 已启动，请轮询 /step4/status 查看进度"}


@router.get("/step4/status")
async def step4_status(db: AsyncSession = Depends(get_db)):
    """检查 Step 4 执行状态。"""
    task_key = "step4"
    task = _tasks.get(task_key)

    if task and not task.done():
        return {"status": "running", "message": "信号补齐执行中（两阶段，耗时较长）..."}

    if task and task.done():
        try:
            result = task.result()
        except Exception as e:
            return {"status": "error", "message": str(e)}
        if result["returncode"] != 0:
            return {
                "status": "error",
                "message": "SQL 执行失败",
                "stderr": result["stderr"],
                "stdout": result["stdout"],
            }

    check = await db.execute(text(_table_exists_sql("dwd_fact_enriched")))
    exists = dict(check.mappings().first())["ok"]
    if not exists:
        return {"status": "not_started", "message": "dwd_fact_enriched 尚未创建"}

    return {"status": "done", "message": "dwd_fact_enriched 已就绪"}


@router.get("/step4/result")
async def step4_result(db: AsyncSession = Depends(get_db)):
    """读取 Step 4 信号补齐统计（从预聚合元数据读取，避免扫描 3000 万行）。"""
    # 优先从元数据读取
    meta = await db.execute(text("""
        SELECT stat_value FROM rebuild2_meta.enrich_result
        WHERE step_code = 'step4_signal_fill' AND stat_key = 'summary'
        ORDER BY created_at DESC LIMIT 1
    """))
    row = meta.mappings().first()
    if row:
        v = row["stat_value"]
        total_rows = v.get("total_rows", 0)

        # 读取 cell_fill 时间差数据
        td_meta = await db.execute(text("""
            SELECT stat_value FROM rebuild2_meta.enrich_result
            WHERE step_code = 'step4_signal_fill' AND stat_key = 'cell_fill_time_delta'
            ORDER BY created_at DESC LIMIT 1
        """))
        td_row = td_meta.mappings().first()
        cell_fill_time_delta = dict(td_row["stat_value"]) if td_row else {}

        return {
            "exists": True,
            "totals": {
                "total_rows": total_rows,
                "rsrp_filled": v.get("rsrp_filled", 0),
                "rsrq_filled": v.get("rsrq_filled", 0),
                "sinr_filled": v.get("sinr_filled", 0),
                "dbm_filled": v.get("dbm_filled", 0),
                "gps_filled": v.get("gps_filled", 0),
            },
            "signal_fill_distribution": v.get("signal_fill_distribution", []),
            "gps_signal_cross": v.get("gps_signal_cross", []),
            "cell_fill_time_delta": cell_fill_time_delta,
        }

    # 回退
    check = await db.execute(text(_table_exists_sql("dwd_fact_enriched")))
    if dict(check.mappings().first())["ok"]:
        return {"exists": True, "totals": {}, "signal_fill_distribution": [],
                "gps_signal_cross": [],
                "_note": "元数据缺失，请重新执行 Step 4 以生成统计"}

    return {"exists": False}


# ─── Step 4 SQL 生成 ──────────────────────────────────────

def _build_step4_sql() -> str:
    """生成 Step 4 信号补齐的完整 SQL 脚本（两阶段）。"""
    return r"""
SET statement_timeout = 0;
SET work_mem = '256MB';
SET max_parallel_workers_per_gather = 0;

-- ============================================================
-- Step 4: 信号补齐（dwd_fact_enriched）
-- Stage 1: 同 Cell 时间最近邻补齐
-- Stage 2: 同 BS 主要 Cell 回退补齐
-- ============================================================

-- 4.1 Stage 1：同 Cell 内 LAG/LEAD 时间最近邻补齐
-- 先物化带行号的 Cell 窗口信号
DROP TABLE IF EXISTS rebuild2._tmp_signal_s1;
CREATE TABLE rebuild2._tmp_signal_s1 AS
SELECT
    l0_row_id,
    op, tech, lac, cell_id, bs_id,
    lon_final, lat_final, gps_source,
    "上报时间",
    "设备标识"  AS dev_id,
    -- 原始信号
    "RSRP"  AS rsrp_raw,
    "RSRQ"  AS rsrq_raw,
    "SINR"  AS sinr_raw,
    "Dbm"   AS dbm_raw,
    -- 窗口：同 Cell 按时间排序，LAG/LEAD 各取最近有效值
    LAG("RSRP")  IGNORE NULLS OVER w AS rsrp_lag,
    LEAD("RSRP") IGNORE NULLS OVER w AS rsrp_lead,
    LAG("RSRQ")  IGNORE NULLS OVER w AS rsrq_lag,
    LEAD("RSRQ") IGNORE NULLS OVER w AS rsrq_lead,
    LAG("SINR")  IGNORE NULLS OVER w AS sinr_lag,
    LEAD("SINR") IGNORE NULLS OVER w AS sinr_lead,
    LAG("Dbm")   IGNORE NULLS OVER w AS dbm_lag,
    LEAD("Dbm")  IGNORE NULLS OVER w AS dbm_lead
FROM rebuild2._tmp_gps_fixed
WINDOW w AS (PARTITION BY op, tech, lac, cell_id ORDER BY "上报时间");

CREATE INDEX ON rebuild2._tmp_signal_s1(op, tech, lac, cell_id);
CREATE INDEX ON rebuild2._tmp_signal_s1(bs_id) WHERE rsrp_raw IS NULL AND rsrp_lag IS NULL AND rsrp_lead IS NULL;
ANALYZE rebuild2._tmp_signal_s1;

-- 4.2 找出同 BS 内记录数最多的主要 Cell（Stage 2 回退目标）
DROP TABLE IF EXISTS rebuild2._tmp_bs_main_cell;
CREATE TABLE rebuild2._tmp_bs_main_cell AS
SELECT DISTINCT ON (op, tech, lac, bs_id)
    op, tech, lac, bs_id, cell_id AS main_cell_id
FROM (
    SELECT op, tech, lac, bs_id, cell_id, count(*) AS cnt
    FROM rebuild2._tmp_gps_fixed
    WHERE "RSRP" IS NOT NULL AND "RSRP" < 0 AND "RSRP" NOT IN (-1, -110)
    GROUP BY op, tech, lac, bs_id, cell_id
) sub
ORDER BY op, tech, lac, bs_id, cnt DESC;

CREATE UNIQUE INDEX ON rebuild2._tmp_bs_main_cell(op, tech, lac, bs_id);
ANALYZE rebuild2._tmp_bs_main_cell;

-- 4.3 主要 Cell 中最近的信号值（时间最近的一条有效信号记录）
-- 用于 Stage 2 回退
DROP TABLE IF EXISTS rebuild2._tmp_main_cell_signal;
CREATE TABLE rebuild2._tmp_main_cell_signal AS
SELECT DISTINCT ON (g.op, g.tech, g.lac, g.bs_id)
    g.op, g.tech, g.lac, g.bs_id,
    g."RSRP"  AS bs_rsrp,
    g."RSRQ"  AS bs_rsrq,
    g."SINR"  AS bs_sinr,
    g."Dbm"   AS bs_dbm
FROM rebuild2._tmp_gps_fixed g
JOIN rebuild2._tmp_bs_main_cell mc
    ON g.op      = mc.op
   AND g.tech    = mc.tech
   AND g.lac     = mc.lac
   AND g.cell_id = mc.main_cell_id
WHERE g."RSRP" IS NOT NULL AND g."RSRP" < 0 AND g."RSRP" NOT IN (-1, -110)
ORDER BY g.op, g.tech, g.lac, g.bs_id, g."上报时间" DESC;

CREATE UNIQUE INDEX ON rebuild2._tmp_main_cell_signal(op, tech, lac, bs_id);
ANALYZE rebuild2._tmp_main_cell_signal;

-- 4.4 组装最终 dwd_fact_enriched
DROP TABLE IF EXISTS rebuild2.dwd_fact_enriched;
CREATE TABLE rebuild2.dwd_fact_enriched AS
SELECT
    s.l0_row_id,
    s.op         AS operator_code,
    s.tech       AS tech_norm,
    s.lac,
    s.cell_id,
    s.bs_id,
    s.lon_final,
    s.lat_final,
    s.gps_source,
    s."上报时间"  AS report_time,
    s.dev_id,
    -- 信号最终值（Stage 1 最近邻，Stage 2 BS 回退）
    COALESCE(
        CASE WHEN s.rsrp_raw IS NOT NULL AND s.rsrp_raw < 0
                  AND s.rsrp_raw NOT IN (-1, -110) THEN s.rsrp_raw END,
        s.rsrp_lag,
        s.rsrp_lead,
        mcs.bs_rsrp
    ) AS rsrp_final,
    COALESCE(
        CASE WHEN s.rsrq_raw IS NOT NULL THEN s.rsrq_raw END,
        s.rsrq_lag,
        s.rsrq_lead,
        mcs.bs_rsrq
    ) AS rsrq_final,
    COALESCE(
        CASE WHEN s.sinr_raw IS NOT NULL THEN s.sinr_raw END,
        s.sinr_lag,
        s.sinr_lead,
        mcs.bs_sinr
    ) AS sinr_final,
    COALESCE(
        CASE WHEN s.dbm_raw IS NOT NULL THEN s.dbm_raw END,
        s.dbm_lag,
        s.dbm_lead,
        mcs.bs_dbm
    ) AS dbm_final,
    -- 信号补齐来源
    CASE
        WHEN s.rsrp_raw IS NOT NULL AND s.rsrp_raw < 0
             AND s.rsrp_raw NOT IN (-1, -110) THEN 'original'
        WHEN COALESCE(s.rsrp_lag, s.rsrp_lead) IS NOT NULL THEN 'cell_fill'
        WHEN mcs.bs_rsrp IS NOT NULL             THEN 'bs_fill'
        ELSE 'unfilled'
    END AS signal_fill_source
FROM rebuild2._tmp_signal_s1 s
LEFT JOIN rebuild2._tmp_main_cell_signal mcs
    ON s.op   = mcs.op
   AND s.tech = mcs.tech
   AND s.lac  = mcs.lac
   AND s.bs_id = mcs.bs_id;

CREATE INDEX ON rebuild2.dwd_fact_enriched(operator_code, tech_norm, lac, cell_id);
CREATE INDEX ON rebuild2.dwd_fact_enriched(operator_code, tech_norm, lac, bs_id);
CREATE INDEX ON rebuild2.dwd_fact_enriched(dev_id);
CREATE INDEX ON rebuild2.dwd_fact_enriched(report_time);
CREATE INDEX ON rebuild2.dwd_fact_enriched(gps_source);
CREATE INDEX ON rebuild2.dwd_fact_enriched(signal_fill_source);
ANALYZE rebuild2.dwd_fact_enriched;

-- 清理临时表（保留 _tmp_gps_fixed 直到 Step 5 完成）
DROP TABLE IF EXISTS rebuild2._tmp_signal_s1;
DROP TABLE IF EXISTS rebuild2._tmp_bs_main_cell;
DROP TABLE IF EXISTS rebuild2._tmp_main_cell_signal;

SELECT 'Step 4 完成: dwd_fact_enriched 已创建' AS status;
"""


# ═══════════════════════════════════════════════════════════
#  Step 5：回算（用修正后 GPS 重算 Cell 和 BS 中心点）
# ═══════════════════════════════════════════════════════════

STEP5_PARAMS = {
    "recalc_source": "dwd_fact_enriched（修正后 GPS）",
    "method": "同 Step 1/2 分箱中位数，但基于修正后经纬度",
    "update_targets": ["rebuild2.dim_cell_refined", "rebuild2.dim_bs_refined"],
    "columns_updated": {
        "dim_cell_refined": ["gps_center_lon_recalc", "gps_center_lat_recalc", "gps_count_recalc"],
        "dim_bs_refined":   ["gps_center_lon_recalc", "gps_center_lat_recalc", "gps_count_recalc"],
    },
    "note": "新增 _recalc 列，不覆盖原始精算值，便于对比",
}


@router.get("/step5/preview")
async def step5_preview(db: AsyncSession = Depends(get_db)):
    """Step 5 预览：查看 dwd_fact_enriched GPS 分布，评估回算价值。"""

    dwd_check = await db.execute(text(_table_exists_sql("dwd_fact_enriched")))
    if not dict(dwd_check.mappings().first())["ok"]:
        return {"ready": False, "error": "请先完成 Step 4（dwd_fact_enriched 尚未就绪）"}

    # GPS 来源统计
    gps_source_result = await db.execute(text("""
        SELECT gps_source, count(*) AS cnt,
            round(count(*) * 100.0 / sum(count(*)) OVER (), 2) AS pct
        FROM rebuild2.dwd_fact_enriched
        GROUP BY gps_source
        ORDER BY cnt DESC
    """))
    gps_sources = [dict(r) for r in gps_source_result.mappings().all()]

    # 有效 GPS 记录统计（用于回算）
    usable_gps_result = await db.execute(text("""
        SELECT
            count(*) FILTER (WHERE lon_final IS NOT NULL) AS rows_with_gps,
            count(*) FILTER (WHERE lon_final IS NULL)     AS rows_no_gps,
            count(DISTINCT CASE WHEN lon_final IS NOT NULL
                THEN (operator_code, tech_norm, lac, cell_id)::text END) AS cells_with_gps,
            count(DISTINCT CASE WHEN lon_final IS NOT NULL
                THEN (operator_code, tech_norm, lac, bs_id)::text END)   AS bs_with_gps
        FROM rebuild2.dwd_fact_enriched
    """))
    usable_gps = dict(usable_gps_result.mappings().first())

    # 与旧中心点比较的预估（Cell 粒度）
    drift_est_result = await db.execute(text("""
        WITH new_cell AS (
            SELECT operator_code, tech_norm, lac, cell_id,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY round(lon_final * 10000)::int) / 10000.0 AS new_lon,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY round(lat_final * 10000)::int) / 10000.0 AS new_lat
            FROM rebuild2.dwd_fact_enriched
            WHERE lon_final IS NOT NULL
            GROUP BY operator_code, tech_norm, lac, cell_id
        )
        SELECT
            count(*)                       AS comparable_cells,
            count(*) FILTER (WHERE
                SQRT(POWER((n.new_lon - cr.gps_center_lon) * 85300, 2) +
                     POWER((n.new_lat - cr.gps_center_lat) * 111000, 2)) > 100
            ) AS drift_gt_100m,
            count(*) FILTER (WHERE
                SQRT(POWER((n.new_lon - cr.gps_center_lon) * 85300, 2) +
                     POWER((n.new_lat - cr.gps_center_lat) * 111000, 2)) > 500
            ) AS drift_gt_500m,
            ROUND(AVG(
                SQRT(POWER((n.new_lon - cr.gps_center_lon) * 85300, 2) +
                     POWER((n.new_lat - cr.gps_center_lat) * 111000, 2))
            )::numeric, 0) AS avg_drift_m
        FROM new_cell n
        JOIN rebuild2.dim_cell_refined cr
            ON n.operator_code = cr.operator_code
           AND n.tech_norm     = cr.tech_norm
           AND n.lac           = cr.lac
           AND n.cell_id       = cr.cell_id
        WHERE cr.gps_center_lon IS NOT NULL
    """))
    drift_est = dict(drift_est_result.mappings().first())

    return {
        "ready": True,
        "params": STEP5_PARAMS,
        "gps_sources": gps_sources,
        "usable_gps": usable_gps,
        "estimated_drift": drift_est,
    }


@router.post("/step5/execute")
async def step5_execute():
    """启动 Step 5 回算（后台 SSH psql 执行）。"""
    task_key = "step5"
    if task_key in _tasks and not _tasks[task_key].done():
        return {"ok": False, "error": "Step 5 正在执行中，请等待完成"}

    sql = _build_step5_sql()

    async def run():
        result = await _ssh_psql(sql)
        _task_results[task_key] = result
        return result

    _tasks[task_key] = asyncio.create_task(run())
    return {"ok": True, "message": "Step 5 已启动，请轮询 /step5/status 查看进度"}


@router.get("/step5/status")
async def step5_status(db: AsyncSession = Depends(get_db)):
    """检查 Step 5 执行状态。"""
    task_key = "step5"
    task = _tasks.get(task_key)

    if task and not task.done():
        return {"status": "running", "message": "回算执行中..."}

    if task and task.done():
        try:
            result = task.result()
        except Exception as e:
            return {"status": "error", "message": str(e)}
        if result["returncode"] != 0:
            return {
                "status": "error",
                "message": "SQL 执行失败",
                "stderr": result["stderr"],
                "stdout": result["stdout"],
            }

    # 检查回算列是否已写入
    check = await db.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'rebuild2'
              AND table_name   = 'dim_cell_refined'
              AND column_name  = 'gps_center_lon_recalc'
        ) AS ok
    """))
    exists = dict(check.mappings().first())["ok"]
    if not exists:
        return {"status": "not_started", "message": "回算列尚未写入 dim_cell_refined"}

    return {"status": "done", "message": "Step 5 回算完成"}


@router.get("/step5/result")
async def step5_result(db: AsyncSession = Depends(get_db)):
    """读取 Step 5 回算对比统计。"""
    check = await db.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'rebuild2'
              AND table_name   = 'dim_cell_refined'
              AND column_name  = 'gps_center_lon_recalc'
        ) AS ok
    """))
    if not dict(check.mappings().first())["ok"]:
        return {"exists": False}

    # Cell 中心点漂移统计
    cell_drift_result = await db.execute(text("""
        SELECT
            count(*) FILTER (WHERE gps_center_lon IS NOT NULL
                AND gps_center_lon_recalc IS NOT NULL)          AS comparable_cells,
            count(*) FILTER (WHERE gps_center_lon_recalc IS NOT NULL
                AND gps_center_lon IS NULL)                     AS newly_covered_cells,
            count(*) FILTER (WHERE
                gps_center_lon IS NOT NULL AND gps_center_lon_recalc IS NOT NULL AND
                SQRT(POWER((gps_center_lon_recalc - gps_center_lon) * 85300, 2) +
                     POWER((gps_center_lat_recalc - gps_center_lat) * 111000, 2)) > 100
            ) AS drift_gt_100m,
            count(*) FILTER (WHERE
                gps_center_lon IS NOT NULL AND gps_center_lon_recalc IS NOT NULL AND
                SQRT(POWER((gps_center_lon_recalc - gps_center_lon) * 85300, 2) +
                     POWER((gps_center_lat_recalc - gps_center_lat) * 111000, 2)) > 500
            ) AS drift_gt_500m,
            ROUND(AVG(
                SQRT(POWER((gps_center_lon_recalc - gps_center_lon) * 85300, 2) +
                     POWER((gps_center_lat_recalc - gps_center_lat) * 111000, 2))
            ) FILTER (WHERE gps_center_lon IS NOT NULL
                AND gps_center_lon_recalc IS NOT NULL)::numeric, 0) AS avg_drift_m
        FROM rebuild2.dim_cell_refined
    """))
    cell_drift = dict(cell_drift_result.mappings().first())

    # BS 中心点漂移统计
    bs_drift_result = await db.execute(text("""
        SELECT
            count(*) FILTER (WHERE gps_center_lon IS NOT NULL
                AND gps_center_lon_recalc IS NOT NULL)          AS comparable_bs,
            count(*) FILTER (WHERE gps_center_lon_recalc IS NOT NULL
                AND gps_center_lon IS NULL)                     AS newly_covered_bs,
            count(*) FILTER (WHERE
                gps_center_lon IS NOT NULL AND gps_center_lon_recalc IS NOT NULL AND
                SQRT(POWER((gps_center_lon_recalc - gps_center_lon) * 85300, 2) +
                     POWER((gps_center_lat_recalc - gps_center_lat) * 111000, 2)) > 100
            ) AS drift_gt_100m,
            count(*) FILTER (WHERE
                gps_center_lon IS NOT NULL AND gps_center_lon_recalc IS NOT NULL AND
                SQRT(POWER((gps_center_lon_recalc - gps_center_lon) * 85300, 2) +
                     POWER((gps_center_lat_recalc - gps_center_lat) * 111000, 2)) > 500
            ) AS drift_gt_500m,
            ROUND(AVG(
                SQRT(POWER((gps_center_lon_recalc - gps_center_lon) * 85300, 2) +
                     POWER((gps_center_lat_recalc - gps_center_lat) * 111000, 2))
            ) FILTER (WHERE gps_center_lon IS NOT NULL
                AND gps_center_lon_recalc IS NOT NULL)::numeric, 0) AS avg_drift_m
        FROM rebuild2.dim_bs_refined
    """))
    bs_drift = dict(bs_drift_result.mappings().first())

    # Top 20 Cell 漂移最大
    top_drift_result = await db.execute(text("""
        SELECT operator_cn, tech_norm, lac, cell_id, bs_id,
            gps_center_lon, gps_center_lat,
            gps_center_lon_recalc, gps_center_lat_recalc,
            ROUND(SQRT(
                POWER((gps_center_lon_recalc - gps_center_lon) * 85300, 2) +
                POWER((gps_center_lat_recalc - gps_center_lat) * 111000, 2)
            )::numeric, 0) AS drift_m
        FROM rebuild2.dim_cell_refined
        WHERE gps_center_lon IS NOT NULL AND gps_center_lon_recalc IS NOT NULL
        ORDER BY drift_m DESC NULLS LAST
        LIMIT 20
    """))
    top_drift = [dict(r) for r in top_drift_result.mappings().all()]

    return {
        "exists": True,
        "cell_drift": cell_drift,
        "bs_drift": bs_drift,
        "top_cell_drifts": top_drift,
    }


# ─── Step 5 SQL 生成 ──────────────────────────────────────

def _build_step5_sql() -> str:
    """生成 Step 5 回算的完整 SQL 脚本。"""
    return r"""
SET statement_timeout = 0;
SET work_mem = '256MB';
SET max_parallel_workers_per_gather = 0;

-- ============================================================
-- Step 5: 回算
-- 基于 dwd_fact_enriched 修正后 GPS 重算 Cell / BS 中心点
-- 新增 _recalc 列，不覆盖原始精算值
-- ============================================================

-- 5.1 按 Cell 重算中心点（分箱中位数，使用修正后 GPS）
DROP TABLE IF EXISTS rebuild2._tmp_cell_recalc;
CREATE TABLE rebuild2._tmp_cell_recalc AS
SELECT
    operator_code, tech_norm, lac, cell_id,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY round(lon_final * 10000)::int)
        / 10000.0 AS new_clon,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY round(lat_final * 10000)::int)
        / 10000.0 AS new_clat,
    count(*) AS gps_count_recalc
FROM rebuild2.dwd_fact_enriched
WHERE lon_final IS NOT NULL
GROUP BY operator_code, tech_norm, lac, cell_id;

CREATE UNIQUE INDEX ON rebuild2._tmp_cell_recalc(operator_code, tech_norm, lac, cell_id);
ANALYZE rebuild2._tmp_cell_recalc;

-- 5.2 按 BS 重算中心点（从 Cell 回算中心聚合）
DROP TABLE IF EXISTS rebuild2._tmp_bs_recalc;
CREATE TABLE rebuild2._tmp_bs_recalc AS
SELECT
    cr.operator_code, cr.tech_norm, cr.lac, cr.bs_id,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY round(rc.new_clon * 10000)::int)
        / 10000.0 AS new_bs_lon,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY round(rc.new_clat * 10000)::int)
        / 10000.0 AS new_bs_lat,
    sum(rc.gps_count_recalc) AS gps_count_recalc
FROM rebuild2.dim_cell_refined cr
JOIN rebuild2._tmp_cell_recalc rc
    ON cr.operator_code = rc.operator_code
   AND cr.tech_norm     = rc.tech_norm
   AND cr.lac           = rc.lac
   AND cr.cell_id       = rc.cell_id
GROUP BY cr.operator_code, cr.tech_norm, cr.lac, cr.bs_id;

CREATE UNIQUE INDEX ON rebuild2._tmp_bs_recalc(operator_code, tech_norm, lac, bs_id);
ANALYZE rebuild2._tmp_bs_recalc;

-- 5.3 写回 dim_cell_refined（新增 _recalc 列）
ALTER TABLE rebuild2.dim_cell_refined
    ADD COLUMN IF NOT EXISTS gps_center_lon_recalc float8,
    ADD COLUMN IF NOT EXISTS gps_center_lat_recalc float8,
    ADD COLUMN IF NOT EXISTS gps_count_recalc       int;

UPDATE rebuild2.dim_cell_refined cr
SET
    gps_center_lon_recalc = rc.new_clon,
    gps_center_lat_recalc = rc.new_clat,
    gps_count_recalc      = rc.gps_count_recalc
FROM rebuild2._tmp_cell_recalc rc
WHERE cr.operator_code = rc.operator_code
  AND cr.tech_norm     = rc.tech_norm
  AND cr.lac           = rc.lac
  AND cr.cell_id       = rc.cell_id;

-- 5.4 写回 dim_bs_refined（新增 _recalc 列）
ALTER TABLE rebuild2.dim_bs_refined
    ADD COLUMN IF NOT EXISTS gps_center_lon_recalc float8,
    ADD COLUMN IF NOT EXISTS gps_center_lat_recalc float8,
    ADD COLUMN IF NOT EXISTS gps_count_recalc       int;

UPDATE rebuild2.dim_bs_refined br
SET
    gps_center_lon_recalc = rc.new_bs_lon,
    gps_center_lat_recalc = rc.new_bs_lat,
    gps_count_recalc      = rc.gps_count_recalc
FROM rebuild2._tmp_bs_recalc rc
WHERE br.operator_code = rc.operator_code
  AND br.tech_norm     = rc.tech_norm
  AND br.lac           = rc.lac
  AND br.bs_id         = rc.bs_id;

-- 清理临时表
DROP TABLE IF EXISTS rebuild2._tmp_cell_recalc;
DROP TABLE IF EXISTS rebuild2._tmp_bs_recalc;
DROP TABLE IF EXISTS rebuild2._tmp_gps_fixed;

SELECT 'Step 5 完成: dim_cell_refined / dim_bs_refined 回算列已更新' AS status;
"""
