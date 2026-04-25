#!/usr/bin/env python3
"""
Step 4/5 并行度扫描（最小化脚本，仅依赖 psycopg，无项目 import）
基线已由 MCP 测定：A=27s B=12s C=25s D=7s（10%抽样）
"""
import threading
import time
import psycopg

DSN = "postgresql://postgres:123456@192.168.200.217:5488/yangca"
WORKERS = [2, 4, 8, 12, 16, 20, 24, 28]

BASELINES = {"A": 27.0, "B": 12.0, "C": 25.0, "D": 7.0}

# ─── SQL 模板（{n}=总分片数，{i}=当前分片） ─────────────────────

A_PAR = """
INSERT INTO rebuild5_bench.enriched_target
SELECT * FROM rebuild5_bench.enriched_records
WHERE cell_id % {n} = {i}
"""

B_PAR = """
INSERT INTO rebuild5_bench.daily_target (
    batch_id, operator_code, lac, bs_id, cell_id,
    obs_date, center_lon, center_lat, obs_count, dev_count
)
SELECT 1, operator_code, lac, bs_id, cell_id,
    DATE(event_time_std),
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lon_final) FILTER (WHERE lon_final IS NOT NULL),
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lat_final) FILTER (WHERE lat_final IS NOT NULL),
    COUNT(*), COUNT(DISTINCT dev_id)
FROM rebuild5_bench.cell_sliding_window
WHERE lon_final IS NOT NULL
  AND cell_id % {n} = {i}
GROUP BY operator_code, lac, bs_id, cell_id, DATE(event_time_std)
"""

C_PAR = """
INSERT INTO rebuild5_bench.metrics_target (
    batch_id, operator_code, lac, bs_id, cell_id,
    center_lon, center_lat,
    independent_obs, distinct_dev_id, gps_valid_count, active_days,
    observed_span_hours, rsrp_avg, rsrq_avg, sinr_avg, pressure_avg,
    max_event_time, window_obs_count
)
SELECT 1, operator_code, lac, bs_id, cell_id,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lon_final) FILTER (WHERE lon_final IS NOT NULL),
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lat_final) FILTER (WHERE lat_final IS NOT NULL),
    COUNT(DISTINCT (cell_id::text || date_trunc('minute', event_time_std)::text)),
    COUNT(DISTINCT dev_id),
    COUNT(*) FILTER (WHERE lon_final IS NOT NULL AND gps_valid),
    COUNT(DISTINCT DATE(event_time_std)),
    EXTRACT(EPOCH FROM MAX(event_time_std) - MIN(event_time_std)) / 3600.0,
    AVG(rsrp_final) FILTER (WHERE rsrp_final BETWEEN -156 AND -1),
    AVG(rsrq_final) FILTER (WHERE rsrq_final BETWEEN -34 AND 10),
    AVG(sinr_final) FILTER (WHERE sinr_final BETWEEN -23 AND 40),
    AVG(pressure_final::double precision) FILTER (WHERE pressure_final IS NOT NULL),
    MAX(event_time_std), COUNT(*)
FROM rebuild5_bench.cell_sliding_window
WHERE cell_id % {n} = {i}
GROUP BY operator_code, lac, bs_id, cell_id
"""

D_PAR = """
WITH radii AS (
    SELECT w.operator_code, w.lac, w.bs_id, w.cell_id,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY
            SQRT(POWER((w.lon_final - m.center_lon) * 85300, 2)
               + POWER((w.lat_final - m.center_lat) * 111000, 2))
        ) AS p50_radius_m,
        PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY
            SQRT(POWER((w.lon_final - m.center_lon) * 85300, 2)
               + POWER((w.lat_final - m.center_lat) * 111000, 2))
        ) AS p90_radius_m
    FROM rebuild5_bench.cell_sliding_window w
    JOIN rebuild5_bench.metrics_target m
      ON m.batch_id = 1
     AND m.operator_code = w.operator_code
     AND m.lac = w.lac AND m.cell_id = w.cell_id
    WHERE w.lon_final IS NOT NULL AND w.gps_valid
      AND m.center_lon IS NOT NULL AND m.center_lat IS NOT NULL
      AND w.cell_id % {n} = {i}
    GROUP BY w.operator_code, w.lac, w.bs_id, w.cell_id
)
UPDATE rebuild5_bench.metrics_target AS t
SET p50_radius_m = r.p50_radius_m,
    p90_radius_m = r.p90_radius_m
FROM radii r
WHERE t.batch_id = 1
  AND t.operator_code = r.operator_code
  AND t.lac = r.lac AND t.cell_id = r.cell_id
  AND t.cell_id % {n} = {i}
"""

# ─── 工具 ─────────────────────────────────────────────────────

def conn():
    return psycopg.connect(DSN, autocommit=True)

def execute_one(sql: str):
    with conn() as c:
        with c.cursor() as cur:
            cur.execute(sql)

def count_table(table: str) -> int:
    with conn() as c:
        with c.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            return cur.fetchone()[0]

def truncate(table: str):
    execute_one(f"TRUNCATE {table}")

def rebuild_metrics():
    """为 D 操作准备干净的质心数据"""
    truncate("rebuild5_bench.metrics_target")
    execute_one(C_PAR.replace("WHERE cell_id % {n} = {i}", "").replace(
        "AND cell_id % {n} = {i}", ""))

def parallel(sql_tmpl: str, n: int) -> tuple[float, list]:
    errs = []
    def worker(i):
        try:
            execute_one(sql_tmpl.format(n=n, i=i))
        except Exception as e:
            errs.append(e)
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    t0 = time.time()
    for t in threads: t.start()
    for t in threads: t.join()
    return time.time() - t0, errs

# ─── 操作配置 ──────────────────────────────────────────────────
OPS = [
    ("A", "纯INSERT",           "rebuild5_bench.enriched_target",  A_PAR, 2504546),
    ("B", "daily_centroids",    "rebuild5_bench.daily_target",     B_PAR, 221716),
    ("C", "cell_metrics",       "rebuild5_bench.metrics_target",   C_PAR, 49448),
]

# ─── 主逻辑 ────────────────────────────────────────────────────
all_results = {}

for label, name, table, sql_tmpl, baseline_rows in OPS:
    baseline = BASELINES[label]
    print(f"\n{'='*55}")
    print(f"操作 {label}: {name}  基线={baseline:.1f}s  期望行数={baseline_rows:,}")
    print(f"{'='*55}")
    results = {}
    for n in WORKERS:
        truncate(table)
        elapsed, errs = parallel(sql_tmpl, n)
        rows = count_table(table)
        ok = (rows == baseline_rows) and not errs
        sp = baseline / elapsed if elapsed > 0 else 0
        results[n] = {"t": elapsed, "sp": sp, "ok": ok, "rows": rows}
        flag = "✓" if ok else f"✗ rows={rows}"
        print(f"  {n:>3}w: {elapsed:>6.2f}s  {sp:>5.1f}x  {flag}")
    all_results[label] = (baseline, results)

# 操作 D（依赖干净的 metrics_target 质心）
print(f"\n{'='*55}")
print(f"操作 D: 半径UPDATE  基线={BASELINES['D']:.1f}s")
print(f"{'='*55}")
baseline_d = BASELINES["D"]
results_d = {}
for n in WORKERS:
    # 重置质心
    truncate("rebuild5_bench.metrics_target")
    execute_one("""
    INSERT INTO rebuild5_bench.metrics_target (
        batch_id, operator_code, lac, bs_id, cell_id,
        center_lon, center_lat,
        independent_obs, distinct_dev_id, gps_valid_count, active_days,
        observed_span_hours, rsrp_avg, rsrq_avg, sinr_avg, pressure_avg,
        max_event_time, window_obs_count
    )
    SELECT 1, operator_code, lac, bs_id, cell_id,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lon_final) FILTER (WHERE lon_final IS NOT NULL),
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY lat_final) FILTER (WHERE lat_final IS NOT NULL),
        COUNT(DISTINCT (cell_id::text || date_trunc('minute', event_time_std)::text)),
        COUNT(DISTINCT dev_id),
        COUNT(*) FILTER (WHERE lon_final IS NOT NULL AND gps_valid),
        COUNT(DISTINCT DATE(event_time_std)),
        EXTRACT(EPOCH FROM MAX(event_time_std) - MIN(event_time_std)) / 3600.0,
        AVG(rsrp_final) FILTER (WHERE rsrp_final BETWEEN -156 AND -1),
        AVG(rsrq_final) FILTER (WHERE rsrq_final BETWEEN -34 AND 10),
        AVG(sinr_final) FILTER (WHERE sinr_final BETWEEN -23 AND 40),
        AVG(pressure_final::double precision) FILTER (WHERE pressure_final IS NOT NULL),
        MAX(event_time_std), COUNT(*)
    FROM rebuild5_bench.cell_sliding_window
    GROUP BY operator_code, lac, bs_id, cell_id
    """)
    elapsed, errs = parallel(D_PAR, n)
    with conn() as c:
        with c.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM rebuild5_bench.metrics_target WHERE p50_radius_m IS NOT NULL")
            rows = cur.fetchone()[0]
    ok = not errs
    sp = baseline_d / elapsed if elapsed > 0 else 0
    results_d[n] = {"t": elapsed, "sp": sp, "ok": ok, "rows": rows}
    flag = "✓" if ok else f"✗ errs={errs}"
    print(f"  {n:>3}w: {elapsed:>6.2f}s  {sp:>5.1f}x  {flag}")

all_results["D"] = (baseline_d, results_d)

# ─── 汇总 ──────────────────────────────────────────────────────
print(f"\n{'='*65}")
print("最终汇总（10%抽样・全量×10估算）")
print(f"{'='*65}")
print(f"{'操作':<20} {'最优N':>6} {'基线(s)':>8} {'优化(s)':>8} {'加速比':>7}")
print("-" * 65)
names_map = {"A":"纯INSERT(Step4)", "B":"daily_centroids", "C":"cell_metrics", "D":"半径UPDATE"}
for label in ["A","B","C","D"]:
    baseline, res = all_results[label]
    best_n = max(res, key=lambda x: res[x]["sp"])
    opt_t = res[best_n]["t"]
    sp = res[best_n]["sp"]
    print(f"{names_map[label]:<20} {best_n:>6} {baseline:>8.1f} {opt_t:>8.2f} {sp:>7.1f}x")
print(f"{'='*65}")
