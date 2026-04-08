# LAC 可信库构建：Phase 1 流程设计（重启版）

> 目的：重启 LAC 分析流程，第一步先构建一套**可信的基础 LAC 候选库**，供后续做 LAC 格式与异常识别、位置精细化验证等使用。

本方案只描述 **Phase 1：筛出“运营商正确 + 格式合理 + 位置在北京 + 时间/访问量稳定”的 LAC 集合**，不再沿用 2025-12-09 日志中旧的分阶段结论。

## 0. 输入数据与关键字段

- 源表：`public."网优cell项目_清洗补齐库_v1"`
- 关键字段（与本阶段相关）：
  - `运营商id`：PLMN 代码（如 `46000`、`46001` 等）
  - `原始lac`：LAC 编码（字符串）
  - `gps`：经纬度信息（后续北京范围过滤使用）
  - `ts`：时间戳（后续时间与访问量过滤使用）
  - 其他：`did` / `ip` 等可用于区分设备或会话，辅助统计“访问量”。

> 复合主键建议：从本阶段开始，尽量以 **(运营商id, 原始lac)** 或 **(network_group, 原始lac)** 作为逻辑主键，避免单独使用 `lac_id`。

## 1. 整体流程概览

Phase 1 的目标，是从全量数据中筛出“结构上看起来可靠的一批 LAC”，具体分 4 层过滤：

1. **运营商过滤**：只保留核心国内运营商（移动 / 联通 / 电信 / 广电 / 铁路专网）。
2. **LAC 格式 & 异常值过滤**：剔除明显错误或非标准的 LAC 编码（具体规则下一步细化）。
3. **位置过滤（北京）**：在格式合格的数据中，只保留 GPS 落在北京范围内的 LAC。
4. **时间 & 访问量过滤**：在北京范围内，再筛选“持续使用、访问量较大”的 LAC，构成 Phase 1 的可信基础库。

本文件重点明确每一步的**目标、输出与 SQL 骨架**，具体阈值和细则可以在实际跑数时再微调。

---

## 2. 步骤一：运营商过滤（只保留核心国内运营商）

### 2.1 目标

- 只保留 **中国境内主流运营商及铁路专网** 的数据，避免国外漫游、异常 PLMN、脏数据干扰。
- 作为第一步，只需要区分：**移动 / 联通 / 电信 / 广电 / 铁路专网**。

### 2.2 核心 PLMN 集合

当前建议只保留以下 5 个占比最大的国内运营商 PLMN（详见 `plmn_core_ops.md`）：

| PLMN代码 | 运营商名称             | 类型       |
|---------|------------------------|------------|
| 46000   | 中国移动               | 移动       |
| 46001   | 中国联通               | 联通       |
| 46011   | 中国电信               | 电信       |
| 46015   | 中国广电               | 广电       |
| 46020   | 中国移动（铁路专用）   | 铁路专网   |

> 说明：未来如有需要，可扩展到 `46002/03/05/06/07/08/09` 等长尾 PLMN，但本阶段先用这 5 个作为“运营商正确”的主集合。

### 2.3 示例：生成“核心运营商”基础视图

```sql
CREATE OR REPLACE VIEW public.v_lac_phase1_step1_operator AS
SELECT *
FROM public."网优cell项目_清洗补齐库_v1"
WHERE "运营商id" IN ('46000','46001','46011','46015','46020');
```

输出：`v_lac_phase1_step1_operator`，只包含核心运营商的数据。

---

## 3. 步骤二：LAC 格式 & 异常值过滤（待细化逻辑）

### 3.1 目标

- 在运营商正确的数据中，进一步过滤掉 **明显错误或无效的 LAC 编码**，例如：
  - 为空 / NULL；
  - 含有明显非数值或非十六进制字符；
  - 长度极端异常（太短或太长）；
  - 特定已知黑名单值（之后根据统计结果补充）。

### 3.2 示例视图骨架（规则待具体填充）

```sql
CREATE OR REPLACE VIEW public.v_lac_phase1_step2_format AS
SELECT *
FROM public.v_lac_phase1_step1_operator
WHERE "原始lac" IS NOT NULL
  -- TODO: 后续补充：LAC 长度、字符集、黑名单等规则
  ;
```

> 下一步计划：单独整理文档，对“LAC 格式和异常值的识别逻辑和分类”做详细设计，然后把具体规则填入这里。

---

## 4. 步骤三：位置过滤（只保留北京范围）

### 4.1 目标

- 在格式合格的数据中，只保留 **GPS 位置落在北京范围** 的记录。
- 依据：`gps` 字段（假设为 `lat,lon` 字符串或可拆分字段）。

### 4.2 示例视图骨架（北京边界示意）

具体经纬度范围可以根据你的实际边界设置，这里仅示意：

```sql
-- 伪代码示例，实际需要根据 gps 字段格式改写
CREATE OR REPLACE VIEW public.v_lac_phase1_step3_beijing AS
SELECT *
FROM public.v_lac_phase1_step2_format
WHERE /* 将 gps 解析成经纬度 lat, lon 之后 */
      /* lat BETWEEN <北京南界> AND <北京北界> */
      /* AND lon BETWEEN <北京西界> AND <北京东界> */;
```

输出：`v_lac_phase1_step3_beijing`，仅含“运营商正确 + 格式合格 + 地理位置在北京”的记录。

---

## 5. 步骤四：时间 & 访问量过滤（寻找稳定且高访问量的 LAC）

### 5.1 目标

- 在“北京 + 格式合格 + 运营商正确”的数据中，识别出：
  - **持续使用**：在一定时间窗口内多天都有访问记录的 LAC；
  - **访问量大**：总记录数或平均日访问量高于设定阈值的 LAC。
- 输出：一批 `(运营商id, 原始lac)` 级别的候选 LAC，作为 **“LAC 可信库 Phase 1”**。

### 5.2 示例聚合逻辑（骨架）

```sql
-- 基于 (运营商id, 原始lac) 聚合出时间与访问量指标
CREATE OR REPLACE VIEW public.v_lac_phase1_step4_stats AS
SELECT
  "运营商id",
  "原始lac",
  COUNT(*) AS total_cnt,
  COUNT(DISTINCT DATE(ts::timestamp)) AS active_days
  -- TODO: 根据需要补充：首次/末次时间、日均访问量等指标
FROM public.v_lac_phase1_step3_beijing
GROUP BY "运营商id", "原始lac";
```

然后再设定“持续使用 + 高访问量”的阈值，例如：

```sql
-- 示例阈值：活跃天数 >= 7 天，且总记录数 >= 1000
CREATE OR REPLACE VIEW public.v_lac_phase1_trusted_candidates AS
SELECT *
FROM public.v_lac_phase1_step4_stats
WHERE active_days >= 7
  AND total_cnt >= 1000;
```

> 注：具体阈值（如天数、访问量）可在实际跑数时根据分布调整，这里只是提供一个可操作的起始框架。

---

## 6. Phase 1 输出与后续工作

- Phase 1 输出视图（建议命名）：
  - `v_lac_phase1_step1_operator`：运营商过滤后的数据；
  - `v_lac_phase1_step2_format`：再经过 LAC 格式过滤的数据；
  - `v_lac_phase1_step3_beijing`：限制在北京范围的数据；
  - `v_lac_phase1_trusted_candidates`：满足时间 + 访问量条件的 LAC 候选集。
- 下一步（单独文档）：
  - 设计并实现 **“LAC 格式和异常值的识别逻辑和分类”**；
  - 将具体规则填入步骤二的 SQL 中；
  - 对 `v_lac_phase1_trusted_candidates` 再做 GPS 精细分布检查，升级为真正的“LAC 可信库 v1”。

