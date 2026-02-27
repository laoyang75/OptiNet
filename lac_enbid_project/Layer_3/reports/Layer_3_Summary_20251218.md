# Layer_3 总览报告（2025-12-18）

本次为“全量执行”后基于 DBHub 的自检与验收汇总，用于“一页拍板”。

## 0) 术语/缩写速查（看表用）

- PASS/WARN/FAIL：通过/告警/阻断（FAIL 为硬阻断；WARN 可继续但需解释与记录）
- report_date：统计日期（日粒度）
- after>before：补齐后缺失字段数大于补齐前（应为 0）
- none/cell_agg/bs_agg：未补齐 / 小区聚合补齐 / 基站聚合补齐
- OVERALL：整体汇总口径
- TopN/Top10：前 N / 前 10（用于抽样展示）

## 1) 本次执行窗口

- 冒烟/全量：全量（Step30~34 + 99）
- report_date 范围：2025-11-30 ~ 2025-12-06
- 输入版本：Layer_2 Step02/04/05/06（固定）

## 2) 结论汇总（一页拍板）

| Step（步骤） | 产物 | 结论（PASS/FAIL/WARN：通过/阻断/告警） | 核心风险摘要 |
|---:|---|---|---|
| 30 | 基站主库 + GPS分级统计 | PASS（通过） | dup=0；中心点合法性=0；collision_suspect=5,815（4.2013%） |
| 31 | 明细 GPS 修正/补齐 | PASS（通过） | src 回溯字段空值=0；Risk（风险）回填占比=0.2575%；Drift（漂移）占比=5.9907% |
| 32 | GPS 修正收益对比 | WARN（告警） | FAIL=0；WARN=72（Risk（风险）/Collision（碰撞）/Risk回填规模需解释+TopN） |
| 33 | 信号补齐（摸底） | PASS（通过） | after>before=0；none（未补齐）=635,651（2.9136%）；bs_agg（基站聚合）=9.0721% |
| 34 | 信号补齐对比 | PASS（通过） | FAIL=0；OVERALL：before=50,714,182 → after=17,652,877 |

## 3) 主要风险 Top3

1. 碰撞疑似基站规模：5,815（4.2013%）（TopN（前N）：`lac_enbid_project/Layer_3/reports/Step30_Report_20251218.md`）
2. Risk（风险）基站回填规模：56,187（0.2575%）（TopN（前N）：`lac_enbid_project/Layer_3/reports/Step31_Report_20251218.md` / `lac_enbid_project/Layer_3/reports/Step32_Report_20251218.md`）
3. 信号 none（未补齐）规模：635,651（2.9136%）（TopN（前N）：`lac_enbid_project/Layer_3/reports/Step33_Report_20251218.md`）

## 4) 下一轮建议（阈值/策略升级点）

- outlier_remove / collision / drift 阈值：建议优先审阅 Step30 离散度 Top10（前10），确定“明显异常”的剔除/降权策略（仅记录，不直接阻断）。
- 原始 GPS 异常值：Step31 Drift→Corrected TopN（前N）出现极端经纬度（如 lon_raw=-78），建议补充“越界/异常坐标”规则，避免污染 drift 统计。
- 信号补齐策略：`sig_rssi_final` 空值率较高（约 75.8%），建议确认该字段是否在源侧天然缺失，或需要独立补齐策略。
