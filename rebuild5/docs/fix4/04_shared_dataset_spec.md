# Fix4 共享样例数据集说明

## 共享数据库

共享样例数据集已经固定在远程数据库：

- 数据库：`ip_loc2`
- schema：`rebuild5_fix4`

说明：

- 这些共享表已经创建完成并写入数据
- 研究线不需要自己建表或导入
- 开始前只需要先核对行数是否一致
- 研究线后续可以在这些共享表之上自由构建派生工作集

## 共享表

### 1. 原始层样例表

- 表名：`rebuild5_fix4.raw_gps_shared_sample`
- 来源：从 `rebuild5.raw_gps_full_backup` 中按共享样例 record_id 抽取
- 当前行数：`1,232,037`

用途：

- 需要从原始 `raw_gps` 开始做 Step1 / Step2 / Step3 / Step4 / Step5 链路时，统一以这张表作为原始输入

### 2. ETL 层样例表

- 表名：`rebuild5_fix4.etl_cleaned_shared_sample`
- 来源：复制自 `rebuild5.etl_cleaned_top10_lac_sample`
- 当前行数：`1,937,395`

用途：

- 需要直接从 ETL 层开始跑 7 批样例链路时，统一使用这张表

### 3. 重点 Cell 清单

- 表名：`rebuild5_fix4.focus_cells_shared`
- 当前行数：`40`

分桶：

- `high_p90 = 10`
- `high_obs = 10`
- `moving = 10`
- `multi_cluster = 10`

用途：

- 用于面积过大、位置失真、多质心 / moving / migration 等重点分析
- 两个 agent 必须使用同一份重点 Cell 清单

## 强制要求

两个独立 agent 必须遵守：

1. 不得替换 `raw_gps_shared_sample`
2. 不得替换 `etl_cleaned_shared_sample`
3. 不得替换 `focus_cells_shared`
4. 如果认为样例不够，只能提交补样建议，不能直接更改这三张共享表

## “样例数据构建”在本轮中的真实含义

本轮文档里写的“样例数据构建”，不是指你去重新定义或替换这三张共享原始表。

它真正指的是：

1. 基于共享原始样例表构建你的派生工作集
2. 明确说明你如何把共享样例拆成：
   - 全链路验证输入
   - 重点 Cell 分析输入
   - 性能压测输入
3. 把这些派生工作集的 SQL / 脚本写清楚，保证可复现

## 推荐使用方式

### 如果需要从原始层完整验证

使用：

- `rebuild5_fix4.raw_gps_shared_sample`

### 如果需要快速做 7 批样例链路验证

使用：

- `rebuild5_fix4.etl_cleaned_shared_sample`

固定时间范围：

- `2025-12-01 ~ 2025-12-07`

### 如果需要重点诊断覆盖面积问题

使用：

- `rebuild5_fix4.focus_cells_shared`

并与样例链路结果联动分析。
