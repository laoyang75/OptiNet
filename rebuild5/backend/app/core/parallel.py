"""并行 SQL 执行器 — 按 cell_id 分片多进程并行。

=== 基准测试结论（beijing_7d 10% 抽样，~250万行，40核服务器）===

第二阶段：策略对比（8进程为基准）
──────────────────────────────────────
操作 4a  enriched_records INSERT (~250万行)
  基线（单线程 INSERT）  16.3s  1.0x
  策略 A: CTAS           12.1s  1.3x  ✓
  策略 C: UNLOGGED       13.4s  1.2x  ✓
  策略 B: 8进程           12.8s  1.3x  ✓
  策略 B+C: UNLOGGED+8p   9.9s  1.6x  ✓  ← 最优（IO密集型）

操作 5a  cell_sliding_window INSERT (~250万行)
  基线                    8.1s  1.0x
  策略 A: CTAS             6.9s  1.2x  ✓
  策略 C: UNLOGGED         5.6s  1.5x  ✓
  策略 B: 8进程             6.5s  1.2x  ✓
  策略 B+C: UNLOGGED+8p    4.8s  1.7x  ✓  ← 最优（IO密集型）

操作 5b  cell_daily_centroids PERCENTILE_CONT (窗口→日粒度聚合)
  基线                   11.3s  1.0x
  策略 A: CTAS             4.5s  2.5x  ✓  ← 最优（PG并行worker）
  策略 B: 8进程             8.0s  1.4x  ✓
  策略 B+C: UNLOGGED+8p    7.5s  1.5x  ✓

操作 5c  cell_metrics PERCENTILE_CONT (多聚合, 窗口→cell)
  基线                   24.8s  1.0x
  策略 A: CTAS            11.1s  2.2x  ✓  ← 最优策略（PG并行worker）
  策略 B: 8进程            16.7s  1.5x  ✓
  策略 B+C: UNLOGGED+8p   16.2s  1.5x  ✓

第三阶段：最优策略核数扫描
──────────────────────────────────────
IO 密集型（UNLOGGED+多进程 INSERT，操作4a/5a）：
  4进程→8进程→12进程(1.7x 拐点)→16进程(退步)→20进程(退步)
  推荐：NUM_WORKERS_INSERT = 12

CPU 密集型（多进程 INSERT，操作5c 仅供参考，生产用CTAS）：
  4→8→12(2.5x)→16(退步)→20(退步)→28(3.6x 最优)
  注：CTAS 方案 PG 内部用16并行worker，无需Python层分片
  推荐：NUM_WORKERS_AGGREGATE = 28（fallback用）

=== 关键技术约束 ===

psycopg % 转义问题彻底解决方案：
  ❌ 之前：混合 %s 参数化 + {shard_filter} 字符串替换 → %%运算符被PG拒绝
  ✅ 现在：所有参数（包括 batch_id 等）全部以 f-string 内联到 SQL
           multiprocessing（非threading）避免GIL限制
           每个进程独立建立 PG 连接

=== 推荐配置 ===

  IO密集型（INSERT为主，无聚合）：
    - 策略：UNLOGGED 目标表 + multiprocessing 分片
    - 推荐：NUM_WORKERS_INSERT = 12
    - 适用：enriched_records INSERT, cell_sliding_window INSERT

  CPU密集型（PERCENTILE_CONT / GROUP BY 聚合）：
    - 策略 A（首选）：CTAS，利用 PG 内置并行 worker（max 16）
    - 策略 B（fallback）：multiprocessing 分片 INSERT，NUM_WORKERS_AGGREGATE = 28
    - 适用：profile_obs, centroid, radius, daily_centroids, cell_metrics
"""
from __future__ import annotations

import multiprocessing
from typing import Any

from .settings import settings

# ── 建议并行度（基准测试结论） ─────────────────────────────────────
NUM_WORKERS_INSERT    = 12   # IO密集型：UNLOGGED + 多进程，12核 ≈ 拐点
NUM_WORKERS_AGGREGATE = 28   # CPU密集型（fallback）：28核，但首选CTAS


def _mp_worker(sql: str) -> str | None:
    """子进程函数。SQL 已完全内联（无 %s 参数化），返回 None=成功，str=错误信息。"""
    import psycopg
    try:
        with psycopg.connect(settings.pg_dsn, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
        return None
    except Exception as e:
        return str(e)


def parallel_execute(
    sql_template: str,
    inline_params: dict[str, Any] | None = None,
    *,
    shard_column: str = 'cell_id',
    shard_table_alias: str = '',   # 如 'p.' 或 'w.'
    num_workers: int = NUM_WORKERS_AGGREGATE,
    where_prefix: str = 'AND',    # 已有 WHERE 子句时用 'AND'，否则用 'WHERE'
) -> None:
    """多进程分片并行执行 SQL。

    【重要】psycopg % 转义问题彻底解决：
      - sql_template 中所有参数均通过 inline_params 以 f-string 格式内联
      - 分片条件 {shard_filter} 也以 f-string 内联
      - 最终发给每个进程的 SQL 不含任何 %s 占位符，避免 psycopg % 转义冲突
      - 使用 multiprocessing（非 threading）绕过 Python GIL

    sql_template 必须包含 {shard_filter} 占位符，会被替换为：
        {where_prefix} {shard_table_alias}{shard_column} % {num_workers} = {shard_id}

    inline_params 中的其他键也会通过 .format(**merged) 内联到 SQL。

    示例（IO密集型，已有 WHERE 子句）：
        parallel_execute(
            \"\"\"
            INSERT INTO rb5.enriched_records (...)
            SELECT {batch_id}::int, ...
            FROM rb5.path_a_records p
            WHERE TRUE
              {shard_filter}
            \"\"\",
            inline_params={"batch_id": batch_id},
            shard_table_alias='p.',
            num_workers=NUM_WORKERS_INSERT,
            where_prefix='AND',
        )

    示例（CPU密集型，无其他 WHERE 子句）：
        parallel_execute(
            \"\"\"
            INSERT INTO rb5.cell_metrics_window (...)
            SELECT ... FROM rb5.cell_sliding_window
            {shard_filter}
            GROUP BY operator_code, lac, bs_id, cell_id
            \"\"\",
            num_workers=NUM_WORKERS_AGGREGATE,
            where_prefix='WHERE',
        )
    """
    params = inline_params or {}
    sqls: list[str] = []
    for shard_id in range(num_workers):
        shard_filter = (
            f"{where_prefix} {shard_table_alias}{shard_column}"
            f" % {num_workers} = {shard_id}"
        )
        merged = {**params, "shard_filter": shard_filter}
        sqls.append(sql_template.format(**merged))

    with multiprocessing.Pool(processes=num_workers) as pool:
        results = pool.map(_mp_worker, sqls)

    errors = [r for r in results if r is not None]
    if errors:
        raise RuntimeError(
            f"parallel_execute 失败（{len(errors)}/{num_workers} 个进程出错）: {errors[0]}"
        )
