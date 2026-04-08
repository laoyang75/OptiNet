# Step35 动态Cell验证（28天原始明细 / Excel格式）RUNBOOK

用途：你在服务器侧按 `Step35_abnormal_cell_scoped_list_375.csv` 这 375 个 `(opt_id, tech_norm, cell_id)` 拉取 **28 天原始明细**（Excel 格式与 `20251225_cellid_28.xlsx` 相同）。等你数据准备好后，我会按本 RUNBOOK 直接做“动态/移动 cell”判定与汇总，不依赖 Layer_3 清洗表。

---

## 1) 输入文件约定（你准备）

### 1.1 目标清单

- `lac_enbid_project/Layer_3/reports/Step35_abnormal_cell_scoped_list_375.csv`
  - 列：`operator_id_raw, tech_norm, cell_id_dec`
  - 行数：375（按本期异常桶命中结果）

### 1.2 28天明细 Excel（你生成）

你提供的 Excel **必须包含以下列**（可多不可少）：

- `ts`：时间戳（可解析为 datetime）
- `cell_id`：cell_id（十进制）
- `opt_id`：运营商（如 46000）
- `dynamic_network_type`：网络制式原字段（示例：`5G_SA` / `LTE`）
- `lgt`：经度（double）
- `ltt`：纬度（double）

可选列（存在则保留，不影响判定）：

- `lac_id`、`rsrp/rsrq/sinr`、`issue_id2`、`primordial_gps` 等

Sheet 命名：

- 推荐 sheet 名：`28d`（与示例一致）
- 如果你仍输出 `14d`，也没问题（我会只用 `28d` 或自动选最大表）

---

## 2) 判定口径（简化版：只要“时间-质心相关/周期切换”就判动态）

你已经明确：准确度不是本轮重点；我们只要把“明显呈现周期性变化”的 cell 从混桶样本里剥离出来。

### 2.1 粒度（重要）

判定对象是 scoped cell：

- `(opt_id, tech_norm, cell_id)`

原因：同一个 `cell_id` 可能在不同运营商/制式下出现（否则会把两套数据混在一起）。

### 2.2 “主导质心”定义（每日）

对每个 `(opt_id, tech_norm, cell_id)`：

1) 把 `lgt/ltt` 坐标做粗网格：`lon_r = round(lgt, 3)`、`lat_r = round(ltt, 3)`（约 100m 级）
2) 每天统计每个 `(lon_r,lat_r)` 的点数
3) 取点数最多的网格作为该天的 **day_major_centroid**
4) 计算该天主导占比：`day_major_share = major_cnt / day_total_cnt`
5) 若 `day_major_share < 0.30`，认为该天“不稳定”，不参与后续切换判定（阈值可调）

### 2.3 “时间相关/切换”判定（28天窗口）

将 28 天按天分成前半/后半（默认 14 天 + 14 天）：

1) 前半的主导质心：统计“每天的 day_major_centroid”，取众数（mode）作为 `half1_centroid`
2) 后半同理：得到 `half2_centroid`
3) 计算两半“主导一致性”（按天占比）：
   - `half1_major_day_share = half1匹配天数 / half1有效天数`
   - `half2_major_day_share = half2匹配天数 / half2有效天数`
4) 计算两半质心距离 `half_major_dist_km`（haversine）

判为动态（`is_dynamic_cell=1`）的最小条件（起步值，可调）：

- `effective_days >= 7`（有效天数足够）
- `half1_major_day_share >= 0.60`
- `half2_major_day_share >= 0.60`
- `half1_centroid != half2_centroid`
- `half_major_dist_km >= 10`

输出时同时给 `dynamic_reason`（例如：`HALF_SWITCH_TIME_CENTROID_CORR` / `INSUFFICIENT_DAYS` 等）。

---

## 3) 你给我数据后，我会交付什么

1) `dynamic_cell_result.csv`：375 行 scoped cell 的判定结果（0/1 + 原因 + 两半质心与距离）
2) `dynamic_cell_summary.md`：
   - 命中数量与占比
   - TopN 距离最大/切换最清晰的样本（便于你快速肉眼确认）
3) （可选）把判定结果回写成 Layer_3 的“异常附加标记表”（不改历史主链路），用于后续排除再分析

---

## 4) 你需要告诉我的两件事（等数据就绪时）

1) 你的 28 天 Excel 路径（在仓库里或服务器路径都行，但我需要能读到）
2) 你是否希望“前半/后半”严格按自然日期（例如 11-27~12-10 / 12-11~12-24），还是按数据最小/最大日期自动切半

