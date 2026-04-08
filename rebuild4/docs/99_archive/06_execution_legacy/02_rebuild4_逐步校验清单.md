# rebuild4 逐步校验清单

状态：执行配套清单
更新时间：2026-04-06

## 1. 文档与真相源

- [ ] 只引用 `rebuild4/docs`
- [ ] 只有一份人工总任务书
- [ ] 数据库事实均注明 PG17 查询来源

## 2. 数据清洗线

- [ ] `field_audit 17/3/7`
- [ ] `target_field 55`
- [ ] `parse_rule/compliance_rule 0/0`
- [ ] ODS `26 vs 24` 与 2 条缺口已入文档
- [ ] trusted 损耗已入正式能力

## 3. 流转线

- [ ] `run/batch/baseline/snapshot/object/fact_layer` 已冻结
- [ ] `data_origin` 仅 `real/synthetic/fallback/empty`
- [ ] compare / governance 定位已冻结
- [ ] 页面/API/表/data_origin 矩阵已冻结

## 4. P0 数据准备

- [ ] 至少 1 个 `real run`
- [ ] 至少 1 个 `real initialization batch`
- [ ] 至少 1 个 `baseline_version`
- [ ] 至少 1 套对象聚合结果
- [ ] 至少 1 套真实 snapshot
- [ ] 至少 1 个真实 incremental batch

## 5. 页面验收

- [ ] `/runs`
- [ ] `/flow/overview`
- [ ] `/flow/snapshot`
- [ ] `/objects`
- [ ] `/baseline`
- [ ] `/initialization`
- [ ] `/governance`
- [ ] `/compare`
- [ ] 画像页

## 6. 链路验收

- [ ] 主流程链 Playwright 通过
- [ ] 支撑治理链 Playwright 通过
- [ ] 页面显示值与 PG17 / API 对齐
