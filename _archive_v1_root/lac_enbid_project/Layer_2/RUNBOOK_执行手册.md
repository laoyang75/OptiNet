# Layer_2 RUNBOOK（执行手册）

面向“服务器手工执行”的一步一步说明：按什么顺序跑、每个 SQL 怎么跑、哪里可能慢、如何做最小冒烟验证、如何验收与回滚。

> 本手册不粘贴 SQL 全文；请直接执行 `lac_enbid_project/Layer_2/sql/` 下的文件。

---

## 0. 执行前检查（必读）

### 0.1 依赖对象必须已存在

输入表（Layer_0）：

- `public."Y_codex_Layer0_Gps_base"`
- `public."Y_codex_Layer0_Lac"`

建议先确认它们在目标库中存在且行数合理（可用 `pg_class.reltuples` 先估计，不必全表 count）。

### 0.2 统一口径（不要改）

- 时间口径：以 `报文时间（ts_std）` 派生的 `上报日期（report_date）` 为准（不是 `cell_ts_std`）
- 制式输出四类：`4G/5G/2_3G/其他`
- 运营商主键：`运营商id_细粒度（operator_id_raw）`；报表视角：`运营商组_提示（operator_group_hint）`
- Step02 行级绝对合规：只要不合规，就不进入 Step03+

### 0.3 服务器配置与会话级调优（建议每次执行前先做）

服务器硬件与 PostgreSQL 全局配置、以及推荐的会话级 `SET` 参数，统一记录在：

- `lac_enbid_project/服务器配置与SQL调优建议.md`

建议：对 L/XL 步骤，优先用 `psql -f` 执行整文件，并在同一会话中先执行该文档里的 `SET`。

### 0.4 一次性迁移与清理（从旧命名到 `Y_codex_Layer2_StepXX_*`）

如果你的数据库里已经存在旧命名对象（例如 `v_layer2_* / d_step* / rpt_step* / anomaly_cell_multi_lac`），但你不想重跑 Step03/05/06 这种 XL 大步骤，可以用**重命名迁移**把已生成对象直接改为新命名（不改变数据内容），并清理冒烟临时表（`*_smoke_*`）。

> 说明：重命名不会破坏依赖；PostgreSQL 会用 OID 维护依赖关系，rename 后视图仍能正常工作。
>
> 注意：部分 SQL 控制台/工具（含某些 MCP 执行器）会按分号拆分语句，导致 `DO $$ ... $$` 这种块执行失败；遇到这种情况建议用 `psql -f` 执行，或改为“先查询对象清单，再逐条 DROP/ALTER”的方式执行迁移。

#### 0.4.1 清理冒烟对象（推荐先做）

```sql
DO $$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT n.nspname, c.relname, c.relkind
    FROM pg_class c
    JOIN pg_namespace n ON n.oid=c.relnamespace
    WHERE n.nspname='public'
      AND c.relname ILIKE '%smoke%'
      -- 安全护栏：只清理本项目产生的 smoke 命名，避免误删其它项目的同名模式
      AND (
        c.relname ILIKE 'rpt\_step%\_smoke\_%' ESCAPE '\'
        OR c.relname ILIKE 'y\_codex\_layer2\_step%\_smoke\_%' ESCAPE '\'
      )
  LOOP
    EXECUTE format(
      'DROP %s IF EXISTS %I.%I CASCADE',
      CASE r.relkind WHEN 'v' THEN 'VIEW' WHEN 'm' THEN 'MATERIALIZED VIEW' ELSE 'TABLE' END,
      r.nspname,
      r.relname
    );
    RAISE NOTICE 'Dropped smoke object: %.% (%).', r.nspname, r.relname, r.relkind;
  END LOOP;
END $$;
```

#### 0.4.2 旧对象重命名为新对象（不重跑大表）

```sql
DO $$
DECLARE r record;
DECLARE old_reg text;
DECLARE new_reg text;
DECLARE old_oid oid;
DECLARE old_kind "char";
BEGIN
  FOR r IN
    SELECT *
    FROM (
      VALUES
        -- Step00
        ('v_layer2_gps_std', 'Y_codex_Layer2_Step00_Gps_Std'),
        ('v_layer2_lac_std', 'Y_codex_Layer2_Step00_Lac_Std'),
        -- Step01
        ('rpt_step1_base_stats_raw', 'Y_codex_Layer2_Step01_BaseStats_Raw'),
        ('rpt_step1_base_stats_valid_cell', 'Y_codex_Layer2_Step01_BaseStats_ValidCell'),
        -- Step02
        ('d_step2_gps_compliance_marked', 'Y_codex_Layer2_Step02_Gps_Compliance_Marked'),
        ('rpt_step2_compliance_diff', 'Y_codex_Layer2_Step02_Compliance_Diff'),
        -- Step03
        ('d_step3_lac_stats_db', 'Y_codex_Layer2_Step03_Lac_Stats_DB'),
        -- Step04
        ('d_step4_master_lac_lib', 'Y_codex_Layer2_Step04_Master_Lac_Lib'),
        -- Step05
        ('d_step5_cellid_stats_db', 'Y_codex_Layer2_Step05_CellId_Stats_DB'),
        ('anomaly_cell_multi_lac', 'Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac'),
        -- Step06
        ('d_step6_l0_lac_filtered', 'Y_codex_Layer2_Step06_L0_Lac_Filtered'),
        ('rpt_step6_gps_vs_lac_compare', 'Y_codex_Layer2_Step06_GpsVsLac_Compare')
    ) AS t(old_name, new_name)
  LOOP
    old_reg := format('public.%I', r.old_name);
    new_reg := format('public.%I', r.new_name);

    old_oid := to_regclass(old_reg);
    IF old_oid IS NULL THEN
      CONTINUE;
    END IF;

    IF to_regclass(new_reg) IS NOT NULL THEN
      RAISE NOTICE 'Skip rename (target exists): % -> %', old_reg, new_reg;
      CONTINUE;
    END IF;

    SELECT c.relkind INTO old_kind FROM pg_class c WHERE c.oid = old_oid;

    IF old_kind = 'v' THEN
      EXECUTE format('ALTER VIEW %s RENAME TO %I', old_reg, r.new_name);
    ELSIF old_kind = 'm' THEN
      EXECUTE format('ALTER MATERIALIZED VIEW %s RENAME TO %I', old_reg, r.new_name);
    ELSE
      EXECUTE format('ALTER TABLE %s RENAME TO %I', old_reg, r.new_name);
    END IF;

    RAISE NOTICE 'Renamed: % -> % (relkind=%).', old_reg, new_reg, old_kind;
  END LOOP;
END $$;
```

#### 0.4.3 迁移后快速验收（建议执行）

```sql
-- 1) smoke 对象应为 0
select count(*) as smoke_objects
from pg_class c
join pg_namespace n on n.oid=c.relnamespace
where n.nspname='public'
  and c.relname ilike '%smoke%';

-- 2) 旧命名对象应为 0（或显著减少）
select c.relkind, c.relname
from pg_class c
join pg_namespace n on n.oid=c.relnamespace
where n.nspname='public'
  and (
    c.relname ilike 'v_layer2_%'
    or c.relname ilike 'd_step%'
    or c.relname ilike 'rpt_step%'
    or c.relname = 'anomaly_cell_multi_lac'
  )
order by c.relname;

-- 3) 新命名对象清单（应包含 Step00~Step06）
select c.relkind, c.relname
from pg_class c
join pg_namespace n on n.oid=c.relnamespace
where n.nspname='public'
  and c.relname ilike 'y_codex_layer2_step%'
order by c.relname;
```

> 迁移完成后，再按本 RUNBOOK 的顺序执行 `sql/00~06_*.sql` 会以新命名为准（脚本内已包含清理旧命名的兼容逻辑）。

---

## 1. 执行顺序（强制）

| 顺序 | Step | SQL 文件 | 产出对象 | 预期耗时 | 建议物化 | 建议先加索引 |
|---:|---|---|---|---|---|---|
| 1 | Step00 | `sql/00_step0_std_views.sql` | 2 个 VIEW | S | 否（默认） | 否 |
| 2 | Step01 | `sql/01_step1_base_stats.sql` | 2 个 TABLE | L | 是（已落表） | 可选（见下） |
| 3 | Step02 | `sql/02_step2_compliance_mark.sql` | 1 VIEW + 1 TABLE | M~L | 合规明细默认 VIEW | 可选 |
| 4 | Step03 | `sql/03_step3_lac_stats_db.sql` | 1 TABLE | XL | 是（已落表） | 否（脚本自带 PK 索引） |
| 5 | Step04 | `sql/04_step4_master_lac_lib.sql` | 1 TABLE | S | 是（已落表） | 否（脚本自带 PK 索引） |
| 6 | Step05 | `sql/05_step5_cellid_stats_and_anomalies.sql` | 1 TABLE + 1 VIEW | XL | 是（已落表） | 否（脚本自带索引） |
| 7 | Step06 | `sql/06_step6_apply_mapping_and_compare.sql` | 1 VIEW + 1 TABLE | XL | 对 LAC_filtered 建议物化（视情况） | 强烈建议（见 Step06） |
| 8 | 未来接口 | `sql/90_future_interfaces_ddl.sql` | 3 张空表结构 | S | 否 | 否 |

耗时等级说明（经验）：S（<1min）/ M（1~10min）/ L（10~30min）/ XL（30min+，建议夜间跑）。

---

## 2. 推荐运行方式（两种任选）

### 2.1 方式 A：psql（推荐，能保留日志）

```bash
psql "$PGURL" -v ON_ERROR_STOP=1 -f lac_enbid_project/Layer_2/sql/00_step0_std_views.sql
psql "$PGURL" -v ON_ERROR_STOP=1 -f lac_enbid_project/Layer_2/sql/01_step1_base_stats.sql
psql "$PGURL" -v ON_ERROR_STOP=1 -f lac_enbid_project/Layer_2/sql/02_step2_compliance_mark.sql
psql "$PGURL" -v ON_ERROR_STOP=1 -f lac_enbid_project/Layer_2/sql/03_step3_lac_stats_db.sql
psql "$PGURL" -v ON_ERROR_STOP=1 -f lac_enbid_project/Layer_2/sql/04_step4_master_lac_lib.sql
psql "$PGURL" -v ON_ERROR_STOP=1 -f lac_enbid_project/Layer_2/sql/05_step5_cellid_stats_and_anomalies.sql
psql "$PGURL" -v ON_ERROR_STOP=1 -f lac_enbid_project/Layer_2/sql/06_step6_apply_mapping_and_compare.sql
```

建议：

- 对 XL 步骤，建议单独跑并记录开始/结束时间。
- 如允许，提前 `SET maintenance_work_mem` / `work_mem` 并观察磁盘临时空间。

### 2.2 方式 B：DBHub / SQL 控制台

按顺序把每个 SQL 文件内容复制到控制台执行即可；建议每步单独执行，便于失败定位与回滚。

---

## 3. 每步“最小可跑模式” vs “全量模式”

你会遇到两类场景：

- **最小可跑模式（冒烟）**：只验证口径与逻辑正确，不追求全量产出；适合白天快速迭代。
- **全量模式**：跑完整输出表；适合夜间/资源充足时。

> 约束：当前 SQL 文件默认都是“全量模式”。最小可跑模式推荐直接执行各 Step 文档里的 `摘要信息（Summary Queries）`，并在输入上加 `report_date` 限制与 `LIMIT`。

每一步的最小可跑模式入口见对应 Step 文档（都给了 5~10 条短 SELECT）。

### 3.1 冒烟落表模式（模板：复制 SQL + 加 report_date 过滤 / LIMIT）

当你需要“下游对象必须存在”（例如想先跑通 Step06 的 join/对比逻辑），但全量 CTAS 太慢时，建议用 **冒烟落表模式**：

1. 复制对应 SQL 文件（例如 Step03/Step05/Step06）到临时脚本或控制台；
2. 把输出对象名改为带后缀的临时对象（例如 `_smoke_20251201`），避免覆盖正式全量表；
3. 在输入处加入 `上报日期（report_date）` 范围过滤，并加 `LIMIT`（白天建议 10~100 万级）；
4. 冒烟验收通过后，再按原 SQL 文件跑全量模式（或按 `report_date` 分天拆分跑）。

模板 1（聚合类 Step03/Step05：在输入处加 report_date + LIMIT）：

```sql
DROP TABLE IF EXISTS public."Y_codex_Layer2_Step03_Lac_Stats_DB_smoke_20251201";
CREATE TABLE public."Y_codex_Layer2_Step03_Lac_Stats_DB_smoke_20251201" AS
SELECT operator_id_raw, operator_group_hint, tech_norm, lac_dec,
       count(*)::bigint as record_count,
       count(*) filter (where has_gps)::bigint as valid_gps_count,
       count(distinct cell_id_dec)::bigint as distinct_cellid_count,
       count(distinct device_id) filter (where device_id is not null)::bigint as distinct_device_count,
       min(ts_std) as first_seen_ts, max(ts_std) as last_seen_ts,
       min(report_date) as first_seen_date, max(report_date) as last_seen_date,
       count(distinct report_date)::int as active_days
FROM (
  SELECT *
  FROM public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"
  WHERE report_date = date '2025-12-01'
  LIMIT 500000
) m
WHERE m.is_compliant
GROUP BY 1,2,3,4;
```

模板 2（join 类 Step06：两边都限流，先验证 join 逻辑）：

```sql
DROP TABLE IF EXISTS public."Y_codex_Layer2_Step06_L0_Lac_Filtered_smoke_20251201";
CREATE TABLE public."Y_codex_Layer2_Step06_L0_Lac_Filtered_smoke_20251201" AS
SELECT l.*
FROM (
  SELECT *
  FROM public."Y_codex_Layer2_Step00_Lac_Std"
  WHERE report_date = date '2025-12-01'
  LIMIT 300000
) l
JOIN public."Y_codex_Layer2_Step05_CellId_Stats_DB" m
  ON l.operator_id_raw=m.operator_id_raw
 AND l.tech_norm=m.tech_norm
 AND l.lac_dec=m.lac_dec
 AND l.cell_id_dec=m.cell_id_dec;
```

提示：

- 如果 `report_date` 过滤仍慢，优先再加 `operator_id_raw='46000'` 之类的单运营商切片。
- 冒烟跑完要清理临时对象（避免占空间），清理顺序参考第 5 节。

---

## 4. 性能与可拆分策略（DBA 视角）

### 4.1 最容易慢的点（优先预案）

- Step03/Step05：大规模聚合（group by） → 典型 XL
- Step06：`L0_Lac` 与映射表 join → 如果 `L0_Lac` 无合适索引，可能非常慢

### 4.2 索引建议（只写建议，不强制执行）

> 注意：在 1e8 级大表上建 BTree 索引本身也可能是 L/XL；建议评估磁盘与维护窗口。

强烈建议（Step06 用）：

- 在 `public."Y_codex_Layer0_Lac"` 上建立复合索引（加速按映射键过滤）：
  - 建议字段：`("运营商id", tech, lac_dec, cell_id_dec)`
  - 目的：让 join 走索引查找而不是全表 hash join

PG15 进阶建议（当你使用 Step00 的标准化字段作为 join key 时）：

- 由于 Step00 中 `operator_id_raw/tech_norm` 来自 `NULLIF(btrim("运营商id"),'')` 与 `CASE tech ... END`，普通索引不一定能被 join 使用；
  可选建立“表达式索引”以对齐标准化 join key（首次创建可能为 L/XL）：
  - `NULLIF(btrim("运营商id"),''), CASE WHEN tech='4G' THEN '4G' ... END, lac_dec, cell_id_dec`
  - 建议加 partial 条件：`WHERE lac_dec IS NOT NULL AND cell_id_dec IS NOT NULL`

> 提示：本仓库的 Step00/Step06 SQL 已内嵌上述索引的 `IF NOT EXISTS` 检查；首次执行可能较慢，但后续迭代重跑会自动跳过。

可选建议（用于按日期拆分跑）：

- 在 `public."Y_codex_Layer0_Gps_base"` 与 `public."Y_codex_Layer0_Lac"` 上对 `ts_std` 建 BRIN 索引（成本低、对时间范围过滤友好）。

### 4.3 拆分跑（按 report_date 分段）

如果全量跑不动，优先按 `上报日期（report_date）` 分段跑（例如一天一跑），再把分段结果 union 汇总。

---

## 5. 失败回滚 / 清理策略（drop 顺序与注意事项）

原则：**先删依赖下游，再删上游**；先删表/物化，再删视图。

推荐清理顺序（从 Step06 往前）：

1. Step06：`DROP TABLE IF EXISTS public."Y_codex_Layer2_Step06_GpsVsLac_Compare";`  
   Step06：`DROP TABLE IF EXISTS public."Y_codex_Layer2_Step06_L0_Lac_Filtered";`（当前脚本默认落表；若历史遗留为 VIEW 请改为 `DROP VIEW`）
2. Step05：`DROP VIEW IF EXISTS public."Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac";`  
   Step05：`DROP TABLE IF EXISTS public."Y_codex_Layer2_Step05_CellId_Stats_DB";`
3. Step04：`DROP TABLE IF EXISTS public."Y_codex_Layer2_Step04_Master_Lac_Lib";`
4. Step03：`DROP TABLE IF EXISTS public."Y_codex_Layer2_Step03_Lac_Stats_DB";`
5. Step02：`DROP TABLE IF EXISTS public."Y_codex_Layer2_Step02_Compliance_Diff";`  
   Step02：`DROP VIEW IF EXISTS public."Y_codex_Layer2_Step02_Gps_Compliance_Marked";`
6. Step01：`DROP TABLE IF EXISTS public."Y_codex_Layer2_Step01_BaseStats_ValidCell";`  
   Step01：`DROP TABLE IF EXISTS public."Y_codex_Layer2_Step01_BaseStats_Raw";`
7. Step00：`DROP VIEW IF EXISTS public."Y_codex_Layer2_Step00_Lac_Std";`  
   Step00：`DROP VIEW IF EXISTS public."Y_codex_Layer2_Step00_Gps_Std";`

注意事项：

- 如果你把某些视图改为表（物化），drop 时注意对象类型一致。
- 清理前建议先把关键报表导出（例如 Step06 对比表、Step05 anomaly 样例）。

---

## 附录 A：MCP 自检记录（由 agent 执行）

本附录记录我在当前数据库连接（MCP/DBHub）上做过的“可复制自检”。  
如果全量查询过慢，本附录会明确标注为 **冒烟模式（LIMIT / 日期限制）**，并给出建议的全量自检方式。

> 自检项清单（对应你的强制要求）：
>
> - 每个输出对象：`count(*)`
> - 每个输出对象：主键重复检查（`count(*)` vs `count(distinct 主键组合)`）
> - Step02：合规前后行数对比 + Top 非合规原因
> - Step03：active_days 分布
> - Step05：anomaly 是否出现；若出现给 10 条样例
> - Step06：GPS vs LAC（raw/filtered） 的行数/去重 cell/lac 对比

### A1. 自检执行模式说明（非常重要）

由于 `Layer_0` 表规模在 1e8 级别，全量 `count(*)/group by/join` 可能耗时较长；本次自检采用 **冒烟模式**，确保“逻辑可跑通、对象可生成、口径可验收”：
（如何把全量 SQL 改成冒烟落表，模板见 §3.1）

- Step00（行级 VIEW）：用 `LIMIT 100000` 做读取与主键采样检查
- Step01（统计表）：基于 `"Y_codex_Layer2_Step00_Gps_Std" LIMIT 2,000,000` 生成
- Step02（合规差异表）：基于 `"Y_codex_Layer2_Step02_Gps_Compliance_Marked" LIMIT 2,000,000` 生成；合规率统计用 `LIMIT 300,000`
- Step03（LAC 汇总库）：基于 `"Y_codex_Layer2_Step02_Gps_Compliance_Marked" LIMIT 2,000,000` 生成
- Step05（映射底座）：基于 `"Y_codex_Layer2_Step02_Gps_Compliance_Marked" LIMIT 300,000` 生成
- Step06（反哺与对比）：
  - `Y_codex_Layer2_Step06_L0_Lac_Filtered` 在自检中 **物化为 TABLE**（来自 `"Y_codex_Layer2_Step00_Lac_Std" LIMIT 300,000`）
  - 对比表用 GPS Raw/合规 + LAC Raw 各 `LIMIT 300,000` 计算

全量模式请按 `sql/00~06_*.sql` 依次执行，并将本附录中的 `LIMIT` 去掉（或按 `report_date` 分天拆分跑）。

### A2. 自检结果（复制自 psql 输出）

自检时间戳：`2025-12-15 13:54:34+08`（Step06 对比表在补齐 `LAC_RAW` 后已刷新）

#### A2.1 每个输出对象：count(*) + 主键重复检查

```text
obj	row_cnt	distinct_*
public."Y_codex_Layer2_Step00_Gps_Std"(sample100k)	100000	100000
public."Y_codex_Layer2_Step00_Lac_Std"(sample100k)	100000	100000
public."Y_codex_Layer2_Step01_BaseStats_Raw"	89	89
public."Y_codex_Layer2_Step01_BaseStats_ValidCell"	16	16
public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"(sample100k)	100000	100000
public."Y_codex_Layer2_Step03_Lac_Stats_DB"	3028	3028
public."Y_codex_Layer2_Step04_Master_Lac_Lib"	3028	3028
public."Y_codex_Layer2_Step05_CellId_Stats_DB"	33425	33425
public."Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac"	28	(视图，无 PK)
public."Y_codex_Layer2_Step06_L0_Lac_Filtered"	13867	13867
public."Y_codex_Layer2_Step06_GpsVsLac_Compare"	702	702
```

说明：

- `sample100k` 表示对 VIEW 仅做 10 万行抽样（验证可读与主键无重复样本）。
- 统计表的 `row_cnt == distinct_pk` 表示主键组合无重复（冒烟数据范围内成立）。

#### A2.2 Step02：合规前后行数对比 + Top 非合规原因

合规率（样本 300,000 行）：

```text
is_compliant	row_cnt
t	68986
f	231014
```

Top 非合规原因（来自 `public."Y_codex_Layer2_Step02_Compliance_Diff"`，样本 2,000,000 行）：

```text
non_compliant_reason	row_cnt
LAC_INVALID;CELLID_NONPOSITIVE	465428
OPERATOR_OUT_OF_SCOPE;LAC_INVALID	362913
LAC_INVALID;CELLID_NULL_OR_NONNUMERIC	209700
OPERATOR_OUT_OF_SCOPE;LAC_INVALID;CELLID_NULL_OR_NONNUMERIC	203491
OPERATOR_OUT_OF_SCOPE;TECH_NOT_4G_5G;LAC_INVALID;CELLID_NULL_OR_NONNUMERIC	90389
OPERATOR_OUT_OF_SCOPE	90005
TECH_NOT_4G_5G;LAC_INVALID;CELLID_NONPOSITIVE	76840
TECH_NOT_4G_5G;CELLID_NULL_OR_NONNUMERIC	30553
TECH_NOT_4G_5G;LAC_INVALID;CELLID_NULL_OR_NONNUMERIC	27602
OPERATOR_OUT_OF_SCOPE;LAC_INVALID;CELLID_NONPOSITIVE	7652
```

#### A2.3 Step03：active_days 分布

```text
active_days	lac_cnt
1	3028
```

说明：该分布来自冒烟样本；全量模式下应看到 1~7 的分布（7 天窗口）。

#### A2.4 Step05：Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac 是否出现 + 10 条样例

anomaly 总数（样本映射表范围内）：

```text
anomaly_cell_cnt
28
```

样例 10 条：

```text
operator_id_raw	tech_norm	cell_id_dec	lac_distinct_cnt	record_count	lac_list_prefix
46000	5G	5767249962	2	7	458784,2097159
46000	5G	5730222083	2	5	2097210,3801120
46000	5G	5687824386	2	5	2097237,5570592
46000	5G	5719916546	2	5	2097353,13172768
46000	5G	5646942209	2	5	2097252,6553632
46000	5G	5637971971	2	5	2097254,6684704
46000	5G	4100255747	2	5	1835040,2097180
46000	5G	5706543107	2	5	2097191,2555936
46000	5G	5782261762	2	5	1441824,2097174
46000	5G	5638217930	2	4	2097252,6553632
```

#### A2.5 Step06：GPS vs LAC（raw/filtered）对比（行数/去重 cell/lac）

说明：Step06 已升级为“反哺（补齐/纠偏）+ 多数据集对比”。旧逻辑里的 `LAC_FILTERED` 已弃用（历史 RUNLOG/样例中若出现，可忽略）。

对比汇总（样本范围）：建议至少能看到 7 类数据集（其中 `LAC_RAW_HAS_CELL_NO_OPERATOR` 用于量化“有 cell 无 operator”的尾巴）。

```text
dataset	sum_row_cnt
GPS_RAW	...
GPS_COMPLIANT	...
LAC_RAW	...
LAC_ELIGIBLE_5PLMN_4G5G_HAS_CELL	...
LAC_SUPPLEMENTED_TRUSTED	...
LAC_SUPPLEMENTED_BACKFILLED	...
LAC_RAW_HAS_CELL_NO_OPERATOR	...
```
