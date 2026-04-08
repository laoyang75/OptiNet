# 服务器配置与 SQL 调优建议（PostgreSQL 15）

> 目的：在编写/评审/执行本项目 SQL 时，明确“机器上限”和“默认会话级调优参数”，避免反复沟通与误判性能瓶颈。

---

## 1) 服务器硬件与 PostgreSQL 配置总结（用于调优参考）

- PostgreSQL 版本：15.13（64-bit）

- 硬件规格：
  - 物理内存：约 264GB
  - CPU：40 核
  - 硬盘类型：SSD（高速 IO，支持高并行度，无明显 IO 瓶颈）
  - 当前系统负载很低（典型 top 显示 95% CPU idle，负载 ~2.x）

- 当前全局关键配置：
  - `max_connections = 100`
  - `shared_buffers = 64GB`（约总内存 25%）
  - `max_parallel_workers = 32`

- 工作负载类型：典型 OLAP/数据仓库场景（复杂分析查询、大 JOIN、GROUP BY、排序、聚合、窗口函数），并发不高（高峰活跃查询预计 20~50），适合更高 `work_mem` 与更积极的并行。

---

## 2) 推荐会话级参数（连接后立即执行）

> 使用方式：在 `psql`/客户端连接后，先执行本段 `SET`；或在每个可执行 SQL 文件顶部保留本段。

```sql
-- OLAP 长查询常见；负载低可禁用超时（或改为 '4h' 更稳）
SET statement_timeout = 0;

-- 关键：减少 sort/hash 落盘（spill）
SET work_mem = '2GB';

-- 加速 CREATE INDEX/大聚合的维护/中间结构
SET maintenance_work_mem = '8GB';
SET max_parallel_maintenance_workers = 8;

-- 鼓励并行（单个大查询尽量吃满 CPU）
SET max_parallel_workers_per_gather = 16;
SET parallel_setup_cost = 0;
SET parallel_tuple_cost = 0.01;

-- PG15：减少 hash join 分批落盘
SET hash_mem_multiplier = 2.0;

-- 常见：JIT 在复杂 ETL/聚合不一定更快，先关（如需再开）
SET jit = off;
```

---

## 3) 重要说明（为什么有些脚本会“覆盖推荐值”）

- 对“产出超大明细表”的 CTAS（例如 Layer_0 重建、Layer_2 Step06 反哺明细）：
  - 并行 worker 可能出现 `MessageQueueSend` 堵塞（worker 推给 leader，但 leader 写入跟不上）。
  - 这类脚本会在文件内显式覆盖部分参数（例如临时关闭并行、关闭 merge join），以换取“可跑完且不炸临时文件”。

---

## 4) 给 AI 的固定提示词（建议每次完整粘贴）

下次让 AI（包括我）帮你写 PostgreSQL 代码时，直接把下面这段完整贴给它，说：
“请根据以下服务器配置和调优建议，在代码中（连接后立即执行）合理设置会话级参数（SET语句），优先使用推荐值，确保性能最优。”

（以上第 1、2 节内容即为固定提示词。）

