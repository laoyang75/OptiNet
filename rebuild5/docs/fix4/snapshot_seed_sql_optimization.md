# `_insert_snapshot_seed_records` SQL 优化分析与修改建议

> 文件：`rebuild5/backend/app/enrichment/pipeline.py`  
> 函数：`_insert_snapshot_seed_records()`（L353–L455）  
> 分析日期：2026-04-20  
> 数据基准：batch_id=7，`candidate_seed_history` 累计 12,331,030 行

---

## 问题定级与优先级排序

| 优先级 | 问题 | 是否确认 | 是否可即时修复 |
|--------|------|---------|--------------|
| 🔴 P1 | `NOT EXISTS` 反查索引不匹配 + 建索引时机错误 | ✅ 已确认 | ✅ 是 |
| 🟡 P2 | `candidate_seed_history` 跨批累计扫描 | ✅ 已确认 | ⚠️ 部分 |
| 🟡 P3 | `new_snapshot_cells` JOIN 放大 / 执行计划选错 | ✅ 已确认（当前 0 行掩盖） | ✅ 是 |

---

## P1：NOT EXISTS 反查索引不匹配 + 建索引时序错误（根因）

### 症状

`_insert_snapshot_seed_records()` 中的核心 anti-join：

```sql
AND NOT EXISTS (
    SELECT 1
    FROM rebuild5.enriched_records er
    WHERE er.batch_id = :batch_id
      AND er.record_id = e.record_id
      AND er.cell_id IS NOT DISTINCT FROM e.cell_id
      AND er.lac IS NOT DISTINCT FROM e.lac
      AND er.tech_norm IS NOT DISTINCT FROM e.tech_norm
)
```

反查需要走 `(batch_id, record_id, cell_id, lac, tech_norm)` 的精确 Index Scan。

### 实际存在的 enriched_records 索引

| 索引名 | 列 | 是否覆盖 NOT EXISTS |
|--------|-----|-------------------|
| `enriched_records_pkey` | `(batch_id, source_row_uid)` | ❌ 无 record_id |
| `idx_enriched_batch` | `(batch_id)` | ❌ 过粗 |
| `idx_enriched_batch_cell` | `(batch_id, operator_code, lac, bs_id, cell_id)` | ❌ 无 record_id，无 tech_norm |

**结论**：三个索引均无法命中 `record_id` 字段，PostgreSQL 只能做 `batch_id` 过滤后的逐行扫描。

### 时序问题（代码层面的双重故障）

```
pipeline.py 执行顺序：

L91:  _insert_enriched_records(...)        ← 写入 enriched_records
L92:  _insert_gps_anomaly_log(...)
L93:  _insert_snapshot_seed_records(...)   ← ❗ NOT EXISTS 此时执行，索引还未建
L94:  CREATE INDEX IF NOT EXISTS idx_enriched_batch        ← 晚了
L98:  CREATE INDEX IF NOT EXISTS idx_enriched_batch_cell   ← 晚了
L114: ANALYZE rebuild5.enriched_records    ← 晚了
```

即使后续在 L94-L113 区块补加了正确索引，对本次执行的 NOT EXISTS 毫无帮助。  
索引只对**下一个 batch** 的运行生效，当前 batch 每次都在裸表上做 anti-join。

### 修改方案

**方案 A（推荐）：在 `ensure_enrichment_schema()` 中预建索引**

在 `schema.py` 的 `ensure_enrichment_schema()` 里，与其他 DDL 一起建好，保证每次 `_insert_snapshot_seed_records()` 运行时索引已存在并 ANALYZE 过：

```sql
CREATE INDEX IF NOT EXISTS idx_enriched_batch_record_cell
ON rebuild5.enriched_records (batch_id, record_id, cell_id, lac, tech_norm);
```

**方案 B：在 `_insert_snapshot_seed_records()` 函数开头显式建索引**

```python
def _insert_snapshot_seed_records(*, batch_id: int, run_id: str) -> None:
    if not relation_exists('rebuild5.candidate_seed_history'):
        return

    # 确保 NOT EXISTS 反查有精确索引，必须在 INSERT 之前
    execute("""
        CREATE INDEX IF NOT EXISTS idx_enriched_batch_record_cell
        ON rebuild5.enriched_records (batch_id, record_id, cell_id, lac, tech_norm)
    """)
    execute('ANALYZE rebuild5.enriched_records')

    execute(f"""INSERT INTO ...""", (run_id, DATASET_KEY))
```

> **推荐方案 A**：schema 层统一管理，不影响函数职责，也避免每次 batch 都重复 ANALYZE。

---

## P2：`candidate_seed_history` 跨批累计扫描

### 规模数据

```
batch 1: 5,682,991 行
batch 2: 2,687,161 行
batch 3: 1,447,986 行
batch 4: 1,024,623 行
batch 5:   803,315 行
batch 6:   684,954 行
─────────────────────
batch<=7 总计：12,331,030 行（1230 万）
```

### 现有索引的结构性问题

现有索引：
```sql
CREATE INDEX idx_candidate_seed_history_cell
ON rebuild5.candidate_seed_history
USING btree (operator_code, lac, bs_id, cell_id, tech_norm, batch_id);
```

JOIN 条件是 `(operator_code, lac, cell_id, tech_norm)`，但索引中 `bs_id` 插在 `cell_id` 前面，**切断了 cell_id 的连续选择性**。`batch_id` 在末尾，范围谓词 `<= :batch_id` 无法有效剪裁。

### 修改方案

补一个贴合 JOIN 键顺序的专用索引（不含 bs_id，batch_id 在尾部做范围收尾）：

```sql
CREATE INDEX IF NOT EXISTS idx_csh_join_batch
ON rebuild5.candidate_seed_history (operator_code, lac, cell_id, tech_norm, batch_id);
```

> 这个索引与现有 idx_candidate_seed_history_cell 并不重复：后者包含 bs_id，前者去掉 bs_id 使连接键连续，PostgreSQL 会选择更优的那个。

### 架构层根因（暂不动）

`WHERE e.batch_id <= :batch_id` 的语义是"汇聚所有历史批次的候选证据"，是 Step 5 数据桥的设计意图，**不能随意改为 `= :batch_id`**，除非 `candidate_seed_history` 本身已是按小区去重聚合的物化表。

如需从架构层解决，需另立专项讨论。

---

## P3：`new_snapshot_cells` JOIN 放大 / 执行计划选错

### 当前状态（batch_id=7）

`new_snapshot_cells` = **0 行**（batch_id=7 无新晋 qualified/excellent 小区），JOIN 早短路，NOT EXISTS 未被触发，整体表现良好。

### 潜在风险

当某 batch 存在大量新晋小区时（例如 batch_1 类型的大批量更新），`new_snapshot_cells` 可能达到数千行，JOIN 后膨胀到数十万行，此时：
1. NOT EXISTS 逐行反查 1230 万行 → 爆炸（P1 问题放大）
2. PostgreSQL 可能对 `new_snapshot_cells`（CTE）和 `candidate_seed_history`（大表）选错 JOIN 策略

### 修改方案

在 `new_snapshot_cells` CTE 上增加 `MATERIALIZED` 关键字，强制物化，防止计划器把 CTE 内联展开后选错 Hash Join / Nested Loop 混用：

```sql
new_snapshot_cells AS MATERIALIZED (
    SELECT ...
    FROM rebuild5.trusted_snapshot_cell s
    LEFT JOIN prev_published p ON ...
    WHERE s.batch_id = :batch_id
      AND s.lifecycle_state IN ('qualified', 'excellent')
      AND p.cell_id IS NULL
)
```

> PostgreSQL 14+ 支持 `AS MATERIALIZED`。强制物化后，`new_snapshot_cells` 的行数在 JOIN 开始前已确定，计划器可以做出更准确的代价估算。

---

## 修改清单汇总

### 文件 1：`rebuild5/backend/app/enrichment/schema.py`

- [ ] 在 `ensure_enrichment_schema()` 中补加：
  ```sql
  CREATE INDEX IF NOT EXISTS idx_enriched_batch_record_cell
  ON rebuild5.enriched_records (batch_id, record_id, cell_id, lac, tech_norm);
  ```

### 文件 2：`rebuild5/backend/app/enrichment/pipeline.py`

- [ ] L94-L113 索引区块：补加候选历史专用 JOIN 索引：
  ```sql
  CREATE INDEX IF NOT EXISTS idx_csh_join_batch
  ON rebuild5.candidate_seed_history (operator_code, lac, cell_id, tech_norm, batch_id);
  ```

- [ ] L353 `_insert_snapshot_seed_records()` 内的 CTE：
  - 将 `new_snapshot_cells AS (` 改为 `new_snapshot_cells AS MATERIALIZED (`

### 可选（ANALYZE 时机）

- [ ] 在 `_insert_enriched_records()` 完成后、调用 `_insert_snapshot_seed_records()` 前，增加：
  ```python
  execute('ANALYZE rebuild5.enriched_records')
  ```
  确保 planner 统计信息及时更新。

---

## 风险说明

| 修改项 | 风险等级 | 说明 |
|--------|---------|------|
| 补 `idx_enriched_batch_record_cell` 索引 | 🟢 低 | DDL 幂等，只读安全 |
| 补 `idx_csh_join_batch` 索引 | 🟢 低 | DDL 幂等，不影响现有查询 |
| `AS MATERIALIZED` CTE | 🟢 低 | 不改语义，只影响执行计划 |
| ANALYZE 提前 | 🟡 中 | 增加轻微 I/O，但换来精确统计 |
| 改 `batch_id <= N` 为 `= N` | 🔴 高 | **禁止，会破坏 Step 5 语义** |
