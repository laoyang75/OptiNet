"""
并行优化基准测试脚本
====================
测试 Step 2/4/5 各操作在不同并行策略下的性能。

用法：
    python bench_parallel.py [--ops op1,op2,...] [--workers 4,8,12,16,20,28]

操作编号：
    4a  - enriched_records INSERT (Step 4)
    5a  - cell_sliding_window INSERT (Step 5)
    5b  - cell_daily_centroids INSERT (Step 5)
    5c  - cell_metrics INSERT (Step 5, PERCENTILE_CONT)
    5d  - cell_metrics UPDATE 半径 (Step 5)
    2a  - profile_obs CTAS (Step 2)
    2b  - profile_centroid CTAS (Step 2)

所有操作在 rebuild5_bench schema 执行，不影响生产数据。
"""
from __future__ import annotations

import multiprocessing
import sys
import time
from typing import Callable

import psycopg

# DB 连接参数
DSN = "postgresql://postgres:123456@192.168.200.217:5488/yangca"

BENCH = "rebuild5_bench"
PROD  = "rebuild5"


# ---------------------------------------------------------------------------
# 连接工具
# ---------------------------------------------------------------------------

def get_conn() -> psycopg.Connection:
    return psycopg.connect(DSN, autocommit=True)


def execute(sql: str, params=None) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)


def fetchone(sql: str, params=None) -> dict | None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            if row is None:
                return None
            cols = [d.name for d in cur.description]
            return dict(zip(cols, row))


# ---------------------------------------------------------------------------
# 核心：可靠的多进程分片执行器（策略 B）
# 完全避免 psycopg % 转义问题：所有参数内联到 SQL
# ---------------------------------------------------------------------------

def _worker_proc(args: tuple) -> str | None:
    """进程函数。返回 None 表示成功，返回 str 表示错误信息。"""
    sql, = args
    try:
        with psycopg.connect(DSN, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
        return None
    except Exception as e:
        return str(e)


def parallel_execute_mp(
    sql_template: str,
    inline_params: dict,          # 用于内联到 SQL 的参数（非 %s）
    shard_column: str = "cell_id",
    shard_table_alias: str = "",  # 如 "p." 或 "w."
    num_workers: int = 8,
    where_prefix: str = "AND",
) -> None:
    """
    多进程分片并行执行。

    关键：shard filter 完全用 f-string 内联，绝不混用 %s 参数化。
    sql_template 中的参数也必须是 inline_params 中的键（用 {key} 占位）。

    示例：
        parallel_execute_mp(
            sql_template=\"\"\"
                INSERT INTO rebuild5_bench.enriched_records_target (...)
                SELECT {batch_id}::int, ...
                FROM rebuild5_bench.path_a_records p
                WHERE TRUE
                  {shard_filter}
            \"\"\",
            inline_params={"batch_id": 1},
            shard_table_alias="p.",
            num_workers=8,
            where_prefix="AND",
        )
    """
    # 准备每个进程的完整 SQL（参数全部内联）
    sqls = []
    for shard_id in range(num_workers):
        shard_filter = (
            f"{where_prefix} {shard_table_alias}{shard_column}"
            f" % {num_workers} = {shard_id}"
        )
        merged = {**inline_params, "shard_filter": shard_filter}
        sqls.append((sql_template.format(**merged),))

    with multiprocessing.Pool(processes=num_workers) as pool:
        results = pool.map(_worker_proc, sqls)

    errors = [r for r in results if r is not None]
    if errors:
        raise RuntimeError(f"并行执行失败（{len(errors)} 个进程出错）: {errors[0]}")


# ---------------------------------------------------------------------------
# 计时工具
# ---------------------------------------------------------------------------

def benchmark(name: str, fn: Callable) -> float:
    print(f"  → {name} ... ", end="", flush=True)
    t0 = time.time()
    fn()
    elapsed = time.time() - t0
    print(f"{elapsed:.1f}s")
    return elapsed


def print_table_header(op_name: str) -> None:
    print(f"\n{'='*68}")
    print(f" 操作：{op_name}")
    print(f"{'='*68}")
    print(f"{'策略':<30} {'耗时':>8} {'加速比':>8} {'正确性':>6}")
    print(f"{'-'*30} {'-'*8} {'-'*8} {'-'*6}")


def print_result(strategy: str, elapsed: float, baseline: float, correct: bool) -> None:
    ratio = baseline / elapsed if elapsed > 0 else 0
    ok = "✓" if correct else "✗"
    print(f"  {strategy:<28} {elapsed:>7.1f}s {ratio:>7.1f}x {ok:>6}")


# ---------------------------------------------------------------------------
# 操作 4a: enriched_records INSERT
# ---------------------------------------------------------------------------

ENRICHED_INSERT_SQL = """
INSERT INTO {schema}.enriched_records_target (
    batch_id, run_id, dataset_key, source_row_uid, record_id, source_table,
    event_time_std, dev_id,
    operator_code, operator_cn, lac, bs_id, cell_id, tech_norm,
    gps_valid, lon_raw, lat_raw,
    lon_final, lat_final, gps_fill_source_final, gps_fill_confidence,
    rsrp_final, rsrp_fill_source_final,
    rsrq_final, rsrq_fill_source_final,
    sinr_final, sinr_fill_source_final,
    pressure_final, pressure_fill_source_final,
    operator_final, operator_fill_source_final,
    lac_final, lac_fill_source_final,
    tech_final, tech_fill_source_final,
    donor_batch_id, donor_snapshot_version, donor_cell_id,
    donor_lifecycle_state, donor_position_grade,
    donor_center_lon, donor_center_lat,
    donor_anchor_eligible, donor_baseline_eligible
)
SELECT
    {batch_id}::int   AS batch_id,
    'bench_run'::text  AS run_id,
    'beijing'::text  AS dataset_key,
    COALESCE(p.source_tid::text, p.record_id) AS source_row_uid,
    p.record_id, p.source_table, p.event_time_std, p.dev_id,
    p.operator_code, p.operator_cn, p.lac, p.bs_id, p.cell_id, p.tech_norm,
    p.gps_valid, p.lon_raw, p.lat_raw,
    COALESCE(p.lon_filled, p.donor_center_lon),
    COALESCE(p.lat_filled, p.donor_center_lat),
    CASE WHEN p.lon_filled IS NOT NULL OR p.lat_filled IS NOT NULL
             THEN COALESCE(p.gps_fill_source, 'none')
         WHEN p.donor_center_lon IS NOT NULL AND p.donor_center_lat IS NOT NULL
             THEN 'trusted_cell'
         ELSE 'none' END,
    CASE WHEN p.lon_filled IS NOT NULL OR p.lat_filled IS NOT NULL THEN NULL
         WHEN p.donor_center_lon IS NOT NULL AND p.donor_center_lat IS NOT NULL
             THEN p.donor_position_grade
         ELSE NULL END,
    COALESCE(p.rsrp_filled, p.donor_rsrp_avg),
    CASE WHEN p.rsrp_filled IS NOT NULL THEN COALESCE(p.rsrp_fill_source, 'none')
         WHEN p.donor_rsrp_avg IS NOT NULL THEN 'trusted_cell' ELSE 'none' END,
    COALESCE(p.rsrq_filled, p.donor_rsrq_avg),
    CASE WHEN p.rsrq_filled IS NOT NULL THEN 'original'
         WHEN p.donor_rsrq_avg IS NOT NULL THEN 'trusted_cell' ELSE 'none' END,
    COALESCE(p.sinr_filled, p.donor_sinr_avg),
    CASE WHEN p.sinr_filled IS NOT NULL THEN 'original'
         WHEN p.donor_sinr_avg IS NOT NULL THEN 'trusted_cell' ELSE 'none' END,
    CASE WHEN p.pressure ~ E'^-?[0-9]+\\.?[0-9]*$' THEN p.pressure::double precision
         ELSE p.donor_pressure_avg END,
    CASE WHEN p.pressure ~ E'^-?[0-9]+\\.?[0-9]*$' THEN 'original'
         WHEN p.donor_pressure_avg IS NOT NULL THEN 'trusted_cell' ELSE 'none' END,
    COALESCE(p.operator_filled, p.donor_operator_code),
    CASE WHEN p.operator_filled IS NOT NULL
             THEN COALESCE(p.operator_fill_source, 'none')
         WHEN p.donor_operator_code IS NOT NULL THEN 'trusted_cell' ELSE 'none' END,
    COALESCE(p.lac_filled, p.donor_lac),
    CASE WHEN p.lac_filled IS NOT NULL
             THEN COALESCE(p.lac_fill_source, 'none')
         WHEN p.donor_lac IS NOT NULL THEN 'trusted_cell' ELSE 'none' END,
    COALESCE(p.tech_norm, p.donor_tech_norm),
    CASE WHEN p.tech_norm IS NOT NULL THEN 'original'
         WHEN p.donor_tech_norm IS NOT NULL THEN 'trusted_cell' ELSE 'none' END,
    p.donor_batch_id, p.donor_snapshot_version, p.donor_cell_id,
    p.donor_lifecycle_state, p.donor_position_grade,
    p.donor_center_lon, p.donor_center_lat,
    p.donor_anchor_eligible, p.donor_baseline_eligible
FROM {bench}.path_a_records p
WHERE TRUE
  {shard_filter}
"""

# CTAS 版本（策略 A — 单 SQL，PG 内部并行 worker）
ENRICHED_CTAS_SQL = """
CREATE TABLE {schema}.enriched_records_target AS
SELECT
    {batch_id}::int   AS batch_id,
    'bench_run'::text  AS run_id,
    'beijing'::text  AS dataset_key,
    COALESCE(p.source_tid::text, p.record_id) AS source_row_uid,
    p.record_id, p.source_table, p.event_time_std, p.dev_id,
    p.operator_code, p.operator_cn, p.lac, p.bs_id, p.cell_id, p.tech_norm,
    p.gps_valid, p.lon_raw, p.lat_raw,
    COALESCE(p.lon_filled, p.donor_center_lon) AS lon_final,
    COALESCE(p.lat_filled, p.donor_center_lat) AS lat_final,
    CASE WHEN p.lon_filled IS NOT NULL OR p.lat_filled IS NOT NULL
             THEN COALESCE(p.gps_fill_source, 'none')
         WHEN p.donor_center_lon IS NOT NULL AND p.donor_center_lat IS NOT NULL
             THEN 'trusted_cell'
         ELSE 'none' END AS gps_fill_source_final,
    CASE WHEN p.lon_filled IS NOT NULL OR p.lat_filled IS NOT NULL THEN NULL
         WHEN p.donor_center_lon IS NOT NULL AND p.donor_center_lat IS NOT NULL
             THEN p.donor_position_grade
         ELSE NULL END AS gps_fill_confidence,
    COALESCE(p.rsrp_filled, p.donor_rsrp_avg) AS rsrp_final,
    CASE WHEN p.rsrp_filled IS NOT NULL THEN COALESCE(p.rsrp_fill_source, 'none')
         WHEN p.donor_rsrp_avg IS NOT NULL THEN 'trusted_cell' ELSE 'none' END AS rsrp_fill_source_final,
    COALESCE(p.rsrq_filled, p.donor_rsrq_avg) AS rsrq_final,
    CASE WHEN p.rsrq_filled IS NOT NULL THEN 'original'
         WHEN p.donor_rsrq_avg IS NOT NULL THEN 'trusted_cell' ELSE 'none' END AS rsrq_fill_source_final,
    COALESCE(p.sinr_filled, p.donor_sinr_avg) AS sinr_final,
    CASE WHEN p.sinr_filled IS NOT NULL THEN 'original'
         WHEN p.donor_sinr_avg IS NOT NULL THEN 'trusted_cell' ELSE 'none' END AS sinr_fill_source_final,
    CASE WHEN p.pressure ~ E'^-?[0-9]+\\.?[0-9]*$' THEN p.pressure::double precision
         ELSE p.donor_pressure_avg END AS pressure_final,
    CASE WHEN p.pressure ~ E'^-?[0-9]+\\.?[0-9]*$' THEN 'original'
         WHEN p.donor_pressure_avg IS NOT NULL THEN 'trusted_cell' ELSE 'none' END AS pressure_fill_source_final,
    COALESCE(p.operator_filled, p.donor_operator_code) AS operator_final,
    CASE WHEN p.operator_filled IS NOT NULL
             THEN COALESCE(p.operator_fill_source, 'none')
         WHEN p.donor_operator_code IS NOT NULL THEN 'trusted_cell' ELSE 'none' END AS operator_fill_source_final,
    COALESCE(p.lac_filled, p.donor_lac) AS lac_final,
    CASE WHEN p.lac_filled IS NOT NULL
             THEN COALESCE(p.lac_fill_source, 'none')
         WHEN p.donor_lac IS NOT NULL THEN 'trusted_cell' ELSE 'none' END AS lac_fill_source_final,
    COALESCE(p.tech_norm, p.donor_tech_norm) AS tech_final,
    CASE WHEN p.tech_norm IS NOT NULL THEN 'original'
         WHEN p.donor_tech_norm IS NOT NULL THEN 'trusted_cell' ELSE 'none' END AS tech_fill_source_final,
    p.donor_batch_id, p.donor_snapshot_version, p.donor_cell_id,
    p.donor_lifecycle_state, p.donor_position_grade,
    p.donor_center_lon, p.donor_center_lat,
    p.donor_anchor_eligible, p.donor_baseline_eligible
FROM {bench}.path_a_records p
"""


def _get_enriched_schema() -> str:
    """从 rb5.enriched_records 获取列定义，建空表"""
    return f"""
    CREATE TABLE IF NOT EXISTS {BENCH}.enriched_records_target
        (LIKE rb5.enriched_records INCLUDING DEFAULTS)
    """


def _verify_enriched(baseline_count: int) -> bool:
    row = fetchone(f"SELECT COUNT(*) AS cnt, AVG(lon_final) AS avg_lon FROM {BENCH}.enriched_records_target")
    ref  = fetchone(f"SELECT COUNT(*) AS cnt, AVG(lon_final) AS avg_lon FROM {BENCH}.enriched_records")
    if not row or not ref:
        return False
    cnt_ok = abs(int(row['cnt']) - baseline_count) < 10
    lon_ok = (row['avg_lon'] is None and ref['avg_lon'] is None) or (
        row['avg_lon'] is not None and ref['avg_lon'] is not None and
        abs(float(row['avg_lon']) - float(ref['avg_lon'])) < 0.001
    )
    return cnt_ok and lon_ok


def bench_op4a_enriched() -> dict:
    """操作 4a: enriched_records INSERT — 测试策略 A/B/C/A+C/B+C"""
    print_table_header("4a | enriched_records INSERT | ~250万行")

    batch_id = 1
    ref_count = int(fetchone(f"SELECT COUNT(*) AS cnt FROM {BENCH}.enriched_records")['cnt'])

    results = {}

    # 清空目标表
    def reset():
        execute(f"DROP TABLE IF EXISTS {BENCH}.enriched_records_target")

    # —— 基线：单线程 INSERT INTO ——
    reset()
    execute(_get_enriched_schema().format(BENCH=BENCH))
    t_base = benchmark("基线（单线程 INSERT）", lambda: execute(
        ENRICHED_INSERT_SQL.format(schema=BENCH, bench=BENCH, batch_id=batch_id, shard_filter="")
    ))
    correct = _verify_enriched(ref_count)
    print_result("基线（单线程 INSERT）", t_base, t_base, correct)
    results["base"] = t_base

    # —— 策略 A: CTAS + RENAME——
    reset()
    t_ctas = benchmark("策略 A: CTAS", lambda: execute(
        ENRICHED_CTAS_SQL.format(schema=BENCH, bench=BENCH, batch_id=batch_id)
    ))
    correct = _verify_enriched(ref_count)
    print_result("策略 A: CTAS", t_ctas, t_base, correct)
    results["ctas"] = t_ctas

    # —— 策略 C: UNLOGGED TABLE + 单线程 INSERT ——
    reset()
    execute(f"""
        CREATE UNLOGGED TABLE {BENCH}.enriched_records_target
            (LIKE rb5.enriched_records INCLUDING DEFAULTS)
    """)
    t_unlog = benchmark("策略 C: UNLOGGED + 单线程", lambda: execute(
        ENRICHED_INSERT_SQL.format(schema=BENCH, bench=BENCH, batch_id=batch_id, shard_filter="")
    ))
    correct = _verify_enriched(ref_count)
    print_result("策略 C: UNLOGGED + 单线程", t_unlog, t_base, correct)
    results["unlogged"] = t_unlog

    # —— 策略 B: 8进程分片 INSERT  ——
    reset()
    execute(_get_enriched_schema().format(BENCH=BENCH))
    t_mp8 = benchmark("策略 B: 8进程分片", lambda: parallel_execute_mp(
        sql_template=ENRICHED_INSERT_SQL.format(schema=BENCH, bench=BENCH, batch_id=batch_id, shard_filter="{shard_filter}"),
        inline_params={},
        shard_table_alias="p.",
        num_workers=8,
        where_prefix="AND",
    ))
    correct = _verify_enriched(ref_count)
    print_result("策略 B: 8进程分片", t_mp8, t_base, correct)
    results["mp8"] = t_mp8

    # —— 策略 B+C: UNLOGGED + 8进程分片 ——
    reset()
    execute(f"""
        CREATE UNLOGGED TABLE {BENCH}.enriched_records_target
            (LIKE rb5.enriched_records INCLUDING DEFAULTS)
    """)
    t_mp8_ul = benchmark("策略 B+C: UNLOGGED+8进程", lambda: parallel_execute_mp(
        sql_template=ENRICHED_INSERT_SQL.format(schema=BENCH, bench=BENCH, batch_id=batch_id, shard_filter="{shard_filter}"),
        inline_params={},
        shard_table_alias="p.",
        num_workers=8,
        where_prefix="AND",
    ))
    correct = _verify_enriched(ref_count)
    print_result("策略 B+C: UNLOGGED+8进程", t_mp8_ul, t_base, correct)
    results["mp8_unlogged"] = t_mp8_ul

    reset()
    return results


# ---------------------------------------------------------------------------
# 操作 5a: cell_sliding_window INSERT
# ---------------------------------------------------------------------------

SLIDING_INSERT_SQL = """
INSERT INTO {schema}.cell_sliding_window_target (
    batch_id, source_row_uid, record_id,
    operator_code, lac, bs_id, cell_id,
    dev_id, event_time_std, gps_valid,
    lon_final, lat_final,
    rsrp_final, rsrq_final, sinr_final, pressure_final,
    source_type
)
SELECT
    {batch_id}, source_row_uid, record_id,
    operator_code, lac, bs_id, cell_id,
    dev_id, event_time_std, gps_valid,
    lon_final, lat_final,
    rsrp_final, rsrq_final, sinr_final, pressure_final,
    'enriched'
FROM {bench}.enriched_records
WHERE batch_id = {batch_id}
  {shard_filter}
"""

SLIDING_CTAS_SQL = """
CREATE TABLE {schema}.cell_sliding_window_target AS
SELECT
    {batch_id} AS batch_id, source_row_uid, record_id,
    operator_code, lac, bs_id, cell_id,
    dev_id, event_time_std, gps_valid,
    lon_final, lat_final,
    rsrp_final, rsrq_final, sinr_final, pressure_final,
    'enriched'::text AS source_type
FROM {bench}.enriched_records
WHERE batch_id = {batch_id}
"""


def bench_op5a_sliding() -> dict:
    """操作 5a: cell_sliding_window INSERT"""
    print_table_header("5a | cell_sliding_window INSERT | ~250万行")

    batch_id = int(fetchone(f"SELECT MAX(batch_id) AS b FROM {BENCH}.enriched_records")['b'])
    ref_count = int(fetchone(f"SELECT COUNT(*) AS cnt FROM {BENCH}.enriched_records WHERE batch_id = {batch_id}")['cnt'])

    results = {}

    def reset():
        execute(f"DROP TABLE IF EXISTS {BENCH}.cell_sliding_window_target")

    # 基线
    reset()
    execute(f"""
        CREATE TABLE {BENCH}.cell_sliding_window_target
            (LIKE rb5.cell_sliding_window INCLUDING DEFAULTS)
    """)
    t_base = benchmark("基线（单线程 INSERT）", lambda: execute(
        SLIDING_INSERT_SQL.format(schema=BENCH, bench=BENCH, batch_id=batch_id, shard_filter="")
    ))
    cnt = int(fetchone(f"SELECT COUNT(*) AS cnt FROM {BENCH}.cell_sliding_window_target")['cnt'])
    correct = abs(cnt - ref_count) < 10
    print_result("基线（单线程 INSERT）", t_base, t_base, correct)
    results["base"] = t_base

    # 策略 A: CTAS
    reset()
    t_ctas = benchmark("策略 A: CTAS", lambda: execute(
        SLIDING_CTAS_SQL.format(schema=BENCH, bench=BENCH, batch_id=batch_id)
    ))
    cnt = int(fetchone(f"SELECT COUNT(*) AS cnt FROM {BENCH}.cell_sliding_window_target")['cnt'])
    correct = abs(cnt - ref_count) < 10
    print_result("策略 A: CTAS", t_ctas, t_base, correct)
    results["ctas"] = t_ctas

    # 策略 C: UNLOGGED
    reset()
    execute(f"""
        CREATE UNLOGGED TABLE {BENCH}.cell_sliding_window_target
            (LIKE rb5.cell_sliding_window INCLUDING DEFAULTS)
    """)
    t_unlog = benchmark("策略 C: UNLOGGED + 单线程", lambda: execute(
        SLIDING_INSERT_SQL.format(schema=BENCH, bench=BENCH, batch_id=batch_id, shard_filter="")
    ))
    cnt = int(fetchone(f"SELECT COUNT(*) AS cnt FROM {BENCH}.cell_sliding_window_target")['cnt'])
    correct = abs(cnt - ref_count) < 10
    print_result("策略 C: UNLOGGED + 单线程", t_unlog, t_base, correct)
    results["unlogged"] = t_unlog

    # 策略 B: 8进程
    reset()
    execute(f"""
        CREATE TABLE {BENCH}.cell_sliding_window_target
            (LIKE rb5.cell_sliding_window INCLUDING DEFAULTS)
    """)
    t_mp8 = benchmark("策略 B: 8进程分片", lambda: parallel_execute_mp(
        sql_template=SLIDING_INSERT_SQL.format(schema=BENCH, bench=BENCH, batch_id=batch_id, shard_filter="{shard_filter}"),
        inline_params={},
        shard_table_alias="",
        num_workers=8,
        where_prefix="AND",
    ))
    cnt = int(fetchone(f"SELECT COUNT(*) AS cnt FROM {BENCH}.cell_sliding_window_target")['cnt'])
    correct = abs(cnt - ref_count) < 10
    print_result("策略 B: 8进程分片", t_mp8, t_base, correct)
    results["mp8"] = t_mp8

    # 策略 B+C
    reset()
    execute(f"""
        CREATE UNLOGGED TABLE {BENCH}.cell_sliding_window_target
            (LIKE rb5.cell_sliding_window INCLUDING DEFAULTS)
    """)
    t_mp8_ul = benchmark("策略 B+C: UNLOGGED+8进程", lambda: parallel_execute_mp(
        sql_template=SLIDING_INSERT_SQL.format(schema=BENCH, bench=BENCH, batch_id=batch_id, shard_filter="{shard_filter}"),
        inline_params={},
        shard_table_alias="",
        num_workers=8,
        where_prefix="AND",
    ))
    cnt = int(fetchone(f"SELECT COUNT(*) AS cnt FROM {BENCH}.cell_sliding_window_target")['cnt'])
    correct = abs(cnt - ref_count) < 10
    print_result("策略 B+C: UNLOGGED+8进程", t_mp8_ul, t_base, correct)
    results["mp8_unlogged"] = t_mp8_ul

    reset()
    return results


# ---------------------------------------------------------------------------
# 操作 5b: cell_daily_centroids INSERT (PERCENTILE_CONT)
# ---------------------------------------------------------------------------

DAILY_CENTROID_INSERT_SQL = """
INSERT INTO {schema}.cell_daily_centroid_target (
    batch_id, operator_code, lac, bs_id, cell_id,
    obs_date, center_lon, center_lat, obs_count, dev_count
)
SELECT
    {batch_id},
    operator_code, lac, bs_id, cell_id,
    DATE(event_time_std) AS obs_date,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lon_final)
        FILTER (WHERE lon_final IS NOT NULL) AS center_lon,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lat_final)
        FILTER (WHERE lat_final IS NOT NULL) AS center_lat,
    COUNT(*) AS obs_count,
    COUNT(DISTINCT dev_id) AS dev_count
FROM {bench}.cell_sliding_window
WHERE lon_final IS NOT NULL
  {shard_filter}
GROUP BY operator_code, lac, bs_id, cell_id, DATE(event_time_std)
"""

DAILY_CENTROID_CTAS_SQL = """
CREATE TABLE {schema}.cell_daily_centroid_target AS
SELECT
    {batch_id} AS batch_id,
    operator_code, lac, bs_id, cell_id,
    DATE(event_time_std) AS obs_date,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lon_final)
        FILTER (WHERE lon_final IS NOT NULL) AS center_lon,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lat_final)
        FILTER (WHERE lat_final IS NOT NULL) AS center_lat,
    COUNT(*) AS obs_count,
    COUNT(DISTINCT dev_id) AS dev_count
FROM {bench}.cell_sliding_window
WHERE lon_final IS NOT NULL
GROUP BY operator_code, lac, bs_id, cell_id, DATE(event_time_std)
"""


def bench_op5b_daily_centroids() -> dict:
    """操作 5b: cell_daily_centroids INSERT + PERCENTILE_CONT"""
    print_table_header("5b | cell_daily_centroids PERCENTILE_CONT | 窗口→日粒度")

    batch_id = 1
    results = {}

    def reset():
        execute(f"DROP TABLE IF EXISTS {BENCH}.cell_daily_centroid_target")

    # 基线
    reset()
    execute(f"""
        CREATE TABLE {BENCH}.cell_daily_centroid_target
            (LIKE rb5.cell_daily_centroid INCLUDING DEFAULTS)
    """)
    t_base = benchmark("基线（单线程 INSERT）", lambda: execute(
        DAILY_CENTROID_INSERT_SQL.format(schema=BENCH, bench=BENCH, batch_id=batch_id, shard_filter="")
    ))
    base_cnt = int(fetchone(f"SELECT COUNT(*) AS cnt FROM {BENCH}.cell_daily_centroid_target")['cnt'])
    base_lon = fetchone(f"SELECT AVG(center_lon) AS v FROM {BENCH}.cell_daily_centroid_target")['v']
    print_result("基线（单线程 INSERT）", t_base, t_base, True)
    results["base"] = t_base

    # 策略 A: CTAS
    reset()
    t_ctas = benchmark("策略 A: CTAS", lambda: execute(
        DAILY_CENTROID_CTAS_SQL.format(schema=BENCH, bench=BENCH, batch_id=batch_id)
    ))
    cnt = int(fetchone(f"SELECT COUNT(*) AS cnt FROM {BENCH}.cell_daily_centroid_target")['cnt'])
    lon = fetchone(f"SELECT AVG(center_lon) AS v FROM {BENCH}.cell_daily_centroid_target")['v']
    correct = abs(cnt - base_cnt) < 10 and (base_lon is None or abs(float(lon) - float(base_lon)) < 0.001)
    print_result("策略 A: CTAS", t_ctas, t_base, correct)
    results["ctas"] = t_ctas

    # 策略 B: 8进程
    reset()
    execute(f"""
        CREATE TABLE {BENCH}.cell_daily_centroid_target
            (LIKE rb5.cell_daily_centroid INCLUDING DEFAULTS)
    """)
    t_mp8 = benchmark("策略 B: 8进程分片", lambda: parallel_execute_mp(
        sql_template=DAILY_CENTROID_INSERT_SQL.format(schema=BENCH, bench=BENCH, batch_id=batch_id, shard_filter="{shard_filter}"),
        inline_params={},
        num_workers=8,
        where_prefix="AND",
    ))
    cnt = int(fetchone(f"SELECT COUNT(*) AS cnt FROM {BENCH}.cell_daily_centroid_target")['cnt'])
    lon = fetchone(f"SELECT AVG(center_lon) AS v FROM {BENCH}.cell_daily_centroid_target")['v']
    correct = abs(cnt - base_cnt) < 10 and (base_lon is None or abs(float(lon) - float(base_lon)) < 0.001)
    print_result("策略 B: 8进程分片", t_mp8, t_base, correct)
    results["mp8"] = t_mp8

    # 策略 B+C: UNLOGGED + 8进程
    reset()
    execute(f"""
        CREATE UNLOGGED TABLE {BENCH}.cell_daily_centroid_target
            (LIKE rb5.cell_daily_centroid INCLUDING DEFAULTS)
    """)
    t_mp8_ul = benchmark("策略 B+C: UNLOGGED+8进程", lambda: parallel_execute_mp(
        sql_template=DAILY_CENTROID_INSERT_SQL.format(schema=BENCH, bench=BENCH, batch_id=batch_id, shard_filter="{shard_filter}"),
        inline_params={},
        num_workers=8,
        where_prefix="AND",
    ))
    cnt = int(fetchone(f"SELECT COUNT(*) AS cnt FROM {BENCH}.cell_daily_centroid_target")['cnt'])
    lon = fetchone(f"SELECT AVG(center_lon) AS v FROM {BENCH}.cell_daily_centroid_target")['v']
    correct = abs(cnt - base_cnt) < 10 and (base_lon is None or abs(float(lon) - float(base_lon)) < 0.001)
    print_result("策略 B+C: UNLOGGED+8进程", t_mp8_ul, t_base, correct)
    results["mp8_unlogged"] = t_mp8_ul

    reset()
    return results


# ---------------------------------------------------------------------------
# 操作 5c: cell_metrics INSERT (多 PERCENTILE_CONT + COUNT DISTINCT)
# ---------------------------------------------------------------------------

METRICS_INSERT_SQL = """
INSERT INTO {schema}.cell_metrics_window_target (
    batch_id, operator_code, lac, bs_id, cell_id,
    center_lon, center_lat,
    independent_obs, distinct_dev_id, gps_valid_count, active_days,
    observed_span_hours,
    rsrp_avg, rsrq_avg, sinr_avg, pressure_avg,
    max_event_time, window_obs_count
)
SELECT
    {batch_id},
    operator_code, lac, bs_id, cell_id,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lon_final)
        FILTER (WHERE lon_final IS NOT NULL) AS center_lon,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lat_final)
        FILTER (WHERE lat_final IS NOT NULL) AS center_lat,
    COUNT(DISTINCT (cell_id::text || date_trunc('minute', event_time_std)::text))
        AS independent_obs,
    COUNT(DISTINCT dev_id) AS distinct_dev_id,
    COUNT(*) FILTER (WHERE lon_final IS NOT NULL AND gps_valid) AS gps_valid_count,
    COUNT(DISTINCT DATE(event_time_std)) AS active_days,
    EXTRACT(EPOCH FROM MAX(event_time_std) - MIN(event_time_std)) / 3600.0
        AS observed_span_hours,
    AVG(rsrp_final) FILTER (WHERE rsrp_final BETWEEN -156 AND -1) AS rsrp_avg,
    AVG(rsrq_final) FILTER (WHERE rsrq_final BETWEEN -34 AND 10) AS rsrq_avg,
    AVG(sinr_final) FILTER (WHERE sinr_final BETWEEN -23 AND 40) AS sinr_avg,
    AVG(pressure_final::double precision)
        FILTER (WHERE pressure_final IS NOT NULL) AS pressure_avg,
    MAX(event_time_std) AS max_event_time,
    COUNT(*) AS window_obs_count
FROM {bench}.cell_sliding_window
{shard_filter}
GROUP BY operator_code, lac, bs_id, cell_id
"""

METRICS_CTAS_SQL = """
CREATE TABLE {schema}.cell_metrics_window_target AS
SELECT
    {batch_id} AS batch_id,
    operator_code, lac, bs_id, cell_id,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lon_final)
        FILTER (WHERE lon_final IS NOT NULL) AS center_lon,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lat_final)
        FILTER (WHERE lat_final IS NOT NULL) AS center_lat,
    COUNT(DISTINCT (cell_id::text || date_trunc('minute', event_time_std)::text))
        AS independent_obs,
    COUNT(DISTINCT dev_id) AS distinct_dev_id,
    COUNT(*) FILTER (WHERE lon_final IS NOT NULL AND gps_valid) AS gps_valid_count,
    COUNT(DISTINCT DATE(event_time_std)) AS active_days,
    EXTRACT(EPOCH FROM MAX(event_time_std) - MIN(event_time_std)) / 3600.0
        AS observed_span_hours,
    AVG(rsrp_final) FILTER (WHERE rsrp_final BETWEEN -156 AND -1) AS rsrp_avg,
    AVG(rsrq_final) FILTER (WHERE rsrq_final BETWEEN -34 AND 10) AS rsrq_avg,
    AVG(sinr_final) FILTER (WHERE sinr_final BETWEEN -23 AND 40) AS sinr_avg,
    AVG(pressure_final::double precision)
        FILTER (WHERE pressure_final IS NOT NULL) AS pressure_avg,
    MAX(event_time_std) AS max_event_time,
    COUNT(*) AS window_obs_count
FROM {bench}.cell_sliding_window
GROUP BY operator_code, lac, bs_id, cell_id
"""


def bench_op5c_cell_metrics() -> dict:
    """操作 5c: cell_metrics INSERT (多 PERCENTILE_CONT)"""
    print_table_header("5c | cell_metrics_window INSERT (多PERCENTILE_CONT) | 窗口→cell聚合")

    batch_id = 1
    results = {}

    def reset():
        execute(f"DROP TABLE IF EXISTS {BENCH}.cell_metrics_window_target")

    def _create_metrics_target(unlogged=False):
        kw = "UNLOGGED" if unlogged else ""
        execute(f"""
            CREATE {kw} TABLE {BENCH}.cell_metrics_window_target (
                batch_id INTEGER,
                operator_code TEXT,
                lac BIGINT,
                bs_id BIGINT,
                cell_id BIGINT,
                center_lon DOUBLE PRECISION,
                center_lat DOUBLE PRECISION,
                independent_obs BIGINT,
                distinct_dev_id BIGINT,
                gps_valid_count BIGINT,
                active_days BIGINT,
                observed_span_hours DOUBLE PRECISION,
                rsrp_avg DOUBLE PRECISION,
                rsrq_avg DOUBLE PRECISION,
                sinr_avg DOUBLE PRECISION,
                pressure_avg DOUBLE PRECISION,
                max_event_time TIMESTAMPTZ,
                window_obs_count BIGINT,
                p50_radius_m DOUBLE PRECISION,
                p90_radius_m DOUBLE PRECISION,
                active_days_30d INTEGER,
                consecutive_inactive_days INTEGER
            )
        """)

    # 基线
    reset()
    _create_metrics_target()
    t_base = benchmark("基线（单线程 INSERT）", lambda: execute(
        METRICS_INSERT_SQL.format(schema=BENCH, bench=BENCH, batch_id=batch_id, shard_filter="")
    ))
    base_cnt = int(fetchone(f"SELECT COUNT(*) AS cnt FROM {BENCH}.cell_metrics_window_target")['cnt'])
    base_lon = fetchone(f"SELECT AVG(center_lon) AS v FROM {BENCH}.cell_metrics_window_target")['v']
    print_result("基线（单线程 INSERT）", t_base, t_base, True)
    results["base"] = t_base

    # 策略 A: CTAS
    reset()
    t_ctas = benchmark("策略 A: CTAS", lambda: execute(
        METRICS_CTAS_SQL.format(schema=BENCH, bench=BENCH, batch_id=batch_id)
    ))
    cnt = int(fetchone(f"SELECT COUNT(*) AS cnt FROM {BENCH}.cell_metrics_window_target")['cnt'])
    lon = fetchone(f"SELECT AVG(center_lon) AS v FROM {BENCH}.cell_metrics_window_target")['v']
    correct = abs(cnt - base_cnt) < 10 and (base_lon is None or abs(float(lon) - float(base_lon)) < 0.001)
    print_result("策略 A: CTAS", t_ctas, t_base, correct)
    results["ctas"] = t_ctas

    # 策略 B: 8进程
    reset()
    _create_metrics_target()
    t_mp8 = benchmark("策略 B: 8进程分片", lambda: parallel_execute_mp(
        sql_template=METRICS_INSERT_SQL.format(schema=BENCH, bench=BENCH, batch_id=batch_id, shard_filter="{shard_filter}"),
        inline_params={},
        num_workers=8,
        where_prefix="WHERE",
    ))
    cnt = int(fetchone(f"SELECT COUNT(*) AS cnt FROM {BENCH}.cell_metrics_window_target")['cnt'])
    lon = fetchone(f"SELECT AVG(center_lon) AS v FROM {BENCH}.cell_metrics_window_target")['v']
    correct = abs(cnt - base_cnt) < 10 and (base_lon is None or abs(float(lon) - float(base_lon)) < 0.001)
    print_result("策略 B: 8进程分片", t_mp8, t_base, correct)
    results["mp8"] = t_mp8

    # 策略 B+C: UNLOGGED + 8进程
    reset()
    _create_metrics_target(unlogged=True)
    t_mp8_ul = benchmark("策略 B+C: UNLOGGED+8进程", lambda: parallel_execute_mp(
        sql_template=METRICS_INSERT_SQL.format(schema=BENCH, bench=BENCH, batch_id=batch_id, shard_filter="{shard_filter}"),
        inline_params={},
        num_workers=8,
        where_prefix="WHERE",
    ))
    cnt = int(fetchone(f"SELECT COUNT(*) AS cnt FROM {BENCH}.cell_metrics_window_target")['cnt'])
    lon = fetchone(f"SELECT AVG(center_lon) AS v FROM {BENCH}.cell_metrics_window_target")['v']
    correct = abs(cnt - base_cnt) < 10 and (base_lon is None or abs(float(lon) - float(base_lon)) < 0.001)
    print_result("策略 B+C: UNLOGGED+8进程", t_mp8_ul, t_base, correct)
    results["mp8_unlogged"] = t_mp8_ul

    reset()
    return results


# ---------------------------------------------------------------------------
# 第三阶段：最优策略核数扫描
# ---------------------------------------------------------------------------

def bench_worker_sweep(
    op_name: str,
    sql_template: str,
    inline_params: dict,
    shard_table_alias: str,
    where_prefix: str,
    create_target_fn,
    reset_fn,
    verify_fn,
    workers_list: list[int],
) -> dict:
    """对最优策略测试不同核数。"""
    print(f"\n{'='*68}")
    print(f" 核数扫描：{op_name}")
    print(f"{'='*68}")
    print(f"{'核数':<8} {'耗时':>8} {'加速比':>8} {'正确性':>6}")
    print(f"{'-'*8} {'-'*8} {'-'*8} {'-'*6}")

    results = {}
    baseline = None

    for n in workers_list:
        reset_fn()
        create_target_fn()
        t = benchmark(f"{n}进程", lambda n=n: parallel_execute_mp(
            sql_template=sql_template,
            inline_params=inline_params,
            shard_table_alias=shard_table_alias,
            num_workers=n,
            where_prefix=where_prefix,
        ))
        if baseline is None:
            baseline = t
        correct = verify_fn()
        ratio = baseline / t if t > 0 else 0
        ok = "✓" if correct else "✗"
        print(f"  {n:<6} {t:>7.1f}s {ratio:>7.1f}x {ok:>6}")
        results[n] = t

    reset_fn()
    return results


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    print("\n" + "="*68)
    print(" rebuild5 并行优化基准测试")
    print(" 测试环境: rebuild5_bench (10% 抽样，~250万行)")
    print("="*68)

    all_results = {}

    # 第二阶段: 逐操作策略对比
    print("\n\n## 第二阶段：策略对比\n")

    r4a = bench_op4a_enriched()
    all_results["4a"] = r4a

    r5a = bench_op5a_sliding()
    all_results["5a"] = r5a

    r5b = bench_op5b_daily_centroids()
    all_results["5b"] = r5b

    r5c = bench_op5c_cell_metrics()
    all_results["5c"] = r5c

    # 汇总最优策略
    print("\n\n## 第二阶段汇总\n")
    print(f"{'操作':<10} {'基线':>8} {'最优策略':<20} {'最优耗时':>8} {'加速比':>8}")
    print(f"{'-'*10} {'-'*8} {'-'*20} {'-'*8} {'-'*8}")

    def best_strategy(r: dict) -> tuple[str, float]:
        base = r.get("base", 9999)
        names = {
            "base": "单线程INSERT",
            "ctas": "CTAS",
            "unlogged": "UNLOGGED",
            "mp8": "8进程",
            "mp8_unlogged": "UNLOGGED+8进程",
        }
        best_k = min((k for k in r if k != "base"), key=lambda k: r[k])
        return names.get(best_k, best_k), r[best_k]

    for op, r in all_results.items():
        base = r.get("base", 0)
        bname, bt = best_strategy(r)
        ratio = base / bt if bt > 0 else 0
        print(f"  {op:<8} {base:>7.1f}s {bname:<20} {bt:>7.1f}s {ratio:>7.1f}x")

    # 第三阶段: 核数扫描（对表现最好的2个操作做扫描）
    print("\n\n## 第三阶段：最优核数扫描\n")

    # 操作 5c (cell_metrics) — CPU密集型：测 4/8/12/16/20/28
    batch_id = 1
    io_workers =  [4, 8, 12, 16, 20]
    cpu_workers = [4, 8, 12, 16, 20, 28]

    def _metrics_reset():
        execute(f"DROP TABLE IF EXISTS {BENCH}.cell_metrics_window_target")

    def _metrics_create():
        execute(f"""
            CREATE UNLOGGED TABLE {BENCH}.cell_metrics_window_target (
                batch_id INTEGER, operator_code TEXT, lac BIGINT, bs_id BIGINT, cell_id BIGINT,
                center_lon DOUBLE PRECISION, center_lat DOUBLE PRECISION,
                independent_obs BIGINT, distinct_dev_id BIGINT, gps_valid_count BIGINT,
                active_days BIGINT, observed_span_hours DOUBLE PRECISION,
                rsrp_avg DOUBLE PRECISION, rsrq_avg DOUBLE PRECISION, sinr_avg DOUBLE PRECISION,
                pressure_avg DOUBLE PRECISION, max_event_time TIMESTAMPTZ, window_obs_count BIGINT,
                p50_radius_m DOUBLE PRECISION, p90_radius_m DOUBLE PRECISION,
                active_days_30d INTEGER, consecutive_inactive_days INTEGER
            )
        """)

    base_cnt_5c = int(fetchone(f"SELECT COUNT(DISTINCT cell_id) AS cnt FROM {BENCH}.cell_sliding_window")['cnt'])

    def _metrics_verify():
        cnt = int(fetchone(f"SELECT COUNT(*) AS cnt FROM {BENCH}.cell_metrics_window_target")['cnt'])
        return abs(cnt - base_cnt_5c) < 100  # GROUP BY cell，允许小误差

    r_sweep_5c = bench_worker_sweep(
        op_name="5c cell_metrics PERCENTILE_CONT (UNLOGGED, CPU密集型)",
        sql_template=METRICS_INSERT_SQL.format(schema=BENCH, bench=BENCH, batch_id=batch_id, shard_filter="{shard_filter}"),
        inline_params={},
        shard_table_alias="",
        where_prefix="WHERE",
        create_target_fn=_metrics_create,
        reset_fn=_metrics_reset,
        verify_fn=_metrics_verify,
        workers_list=cpu_workers,
    )
    all_results["sweep_5c"] = r_sweep_5c

    # 操作 4a (enriched INSERT) — IO密集型：测 4/8/12/16/20
    def _enriched_reset():
        execute(f"DROP TABLE IF EXISTS {BENCH}.enriched_records_target")

    def _enriched_create():
        execute(f"""
            CREATE UNLOGGED TABLE {BENCH}.enriched_records_target
                (LIKE rb5.enriched_records INCLUDING DEFAULTS)
        """)

    ref_cnt_4a = int(fetchone(f"SELECT COUNT(*) AS cnt FROM {BENCH}.enriched_records")['cnt'])

    def _enriched_verify():
        cnt = int(fetchone(f"SELECT COUNT(*) AS cnt FROM {BENCH}.enriched_records_target")['cnt'])
        return abs(cnt - ref_cnt_4a) < 10

    r_sweep_4a = bench_worker_sweep(
        op_name="4a enriched_records INSERT (UNLOGGED, IO密集型)",
        sql_template=ENRICHED_INSERT_SQL.format(schema=BENCH, bench=BENCH, batch_id=1, shard_filter="{shard_filter}"),
        inline_params={},
        shard_table_alias="p.",
        where_prefix="AND",
        create_target_fn=_enriched_create,
        reset_fn=_enriched_reset,
        verify_fn=_enriched_verify,
        workers_list=io_workers,
    )
    all_results["sweep_4a"] = r_sweep_4a

    # 最终推荐
    print("\n\n## 最终推荐配置\n")

    def find_optimal_workers(sweep: dict) -> int:
        """找到边际收益递减的拐点"""
        items = sorted(sweep.items())
        if not items:
            return 8
        best_t = min(v for v in sweep.values())
        for n, t in items:
            if t <= best_t * 1.05:  # 5% 以内认为是拐点
                return n
        return items[-1][0]

    opt_5c = find_optimal_workers(r_sweep_5c)
    opt_4a = find_optimal_workers(r_sweep_4a)

    print(f"  IO密集型 (enriched INSERT, sliding_window INSERT):")
    print(f"    推荐核数: NUM_WORKERS_INSERT = {opt_4a}")
    print(f"    最优耗时: {r_sweep_4a.get(opt_4a, '?'):.1f}s (vs 基线 {all_results['4a']['base']:.1f}s)")

    print(f"\n  CPU密集型 (PERCENTILE_CONT 聚合):")
    print(f"    推荐核数: NUM_WORKERS_AGGREGATE = {opt_5c}")
    print(f"    最优耗时: {r_sweep_5c.get(opt_5c, '?'):.1f}s (vs 基线 {all_results['5c']['base']:.1f}s)")

    print(f"\n  推荐写入 parallel.py:")
    print(f"    NUM_WORKERS_INSERT    = {opt_4a}")
    print(f"    NUM_WORKERS_AGGREGATE = {opt_5c}")

    print("\n\n✅ 测试完成。请确认后运行：DROP SCHEMA rebuild5_bench CASCADE")


if __name__ == "__main__":
    multiprocessing.set_start_method("spawn", force=True)
    main()
