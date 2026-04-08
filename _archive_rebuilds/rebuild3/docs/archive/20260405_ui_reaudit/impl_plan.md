# 最终实施任务书（Gate B）

> 当前版本聚焦样本阶段 Gate A-E；Gate F/G 在样本确认通过后展开。

## 阶段与门禁

- Gate A：文档与 UI 对齐完成
- Gate B：目录、独立 schema、配置与项目骨架完成
- Gate C：样本数据集定义完成
- Gate D：rebuild2 / rebuild3 样本双跑完成
- Gate E：样本偏差评估通过
- Gate F：全量运行完成（等待 Gate E 人工确认）
- Gate G：全量偏差评估完成（等待 Gate F）

## 任务域 A：schema 与元数据

### A1. 独立 schema 与核心表
- 输入：冻结文档、最终补丁、当前 PG17 实际资产结构
- 输出：`rebuild3` / `rebuild3_meta` / `rebuild3_sample` / `rebuild3_sample_meta` DDL
- 依赖：Gate A
- 验收标准：所有 rebuild3 正式/样本表均不写入 `rebuild2*`
- 风险：样本/正式表结构漂移
- 回归影响：影响所有后续脚本与 API
- 推荐顺序：最高

### A2. 批次快照与治理元数据
- 输入：UI v2 读模型需求、最终补丁
- 输出：`run`、`batch`、`baseline_version`、`batch_snapshot`、`batch_*_summary`、`asset_*` 表
- 依赖：A1
- 验收标准：可支撑样本运行记录与基础数据治理最小接口
- 风险：字段不够覆盖后续 UI
- 回归影响：影响运行中心/流转总览/治理页
- 推荐顺序：高

## 任务域 B：后端与编排

### B1. 样本执行编排脚本
- 输入：样本 scope、DDL、SQL 链路
- 输出：`run_sample_pipeline.py`
- 依赖：A1/A2
- 验收标准：单命令可完成样本抽取、rebuild2 rerun、rebuild3 rerun、报告输出
- 风险：SQL 失败回滚与重跑不完整
- 回归影响：影响 Gate C-E
- 推荐顺序：最高

### B2. rebuild2 样本 rerun
- 输入：样本 `l0_lac` / `l0_gps`
- 输出：sample eval 版 `r2_*` 事实/对象/画像/状态表
- 依赖：B1
- 验收标准：不写回 `rebuild2`，可输出稳定 compare 基线
- 风险：微缩样本与 full-threshold 不可比
- 回归影响：影响 Gate D/E
- 推荐顺序：高

### B3. rebuild3 样本最小闭环
- 输入：样本 `l0_lac`
- 输出：`fact_standardized`、四分流、`obj_*`、`baseline_*`、`batch_*` 汇总
- 依赖：A1/A2/B1
- 验收标准：样本可真实跑通，带版本上下文
- 风险：状态/资格判定过于简化
- 回归影响：影响 Gate D/E
- 推荐顺序：高

## 任务域 C：读模型与 API

### C1. 最小 FastAPI 骨架与读模型约定
- 输入：UI v2 读模型文档
- 输出：`run.py`、`object.py`、`compare.py`、`governance.py` 最小 API 骨架与类型说明
- 依赖：A2
- 验收标准：路径/返回模型清晰，后续可直接接真实 SQL
- 风险：本机未安装依赖，当前仅做静态骨架
- 回归影响：影响前端接入
- 推荐顺序：中

## 任务域 D：前端

### D1. Vue 3 + TypeScript + Vite 最小骨架
- 输入：技术栈冻结文档
- 输出：最小 `frontend/` scaffold
- 依赖：无
- 验收标准：目录结构、依赖声明、入口文件齐全
- 风险：当前环境未安装 npm 依赖
- 回归影响：低
- 推荐顺序：中

## 任务域 E：验证与对比

### E1. 样本切片定义
- 输入：sample 候选对象分布、异常分布、冻结文档覆盖要求
- 输出：`sample_scope.md` + 样本 scope 表
- 依赖：A1/A2
- 验收标准：覆盖 active / waiting / observing / issue / rejected / baseline
- 风险：`migration_suspect` 未覆盖
- 回归影响：影响 Gate C-E
- 推荐顺序：最高

### E2. 样本运行记录与偏差评估
- 输入：B2/B3 结果
- 输出：`sample_run_report.md`、`sample_compare_report.md`
- 依赖：E1/B2/B3
- 验收标准：对比报告给出差异分类、阻塞判断与 Gate E 结论
- 风险：样本特有噪声放大偏差
- 回归影响：直接决定能否进入 Gate F
- 推荐顺序：最高

### E3. 全量运行与全量偏差评估
- 输入：Gate E 通过确认
- 输出：`full_run_report.md`、`full_compare_report.md`
- 依赖：用户确认通过 Gate E
- 验收标准：Gate F/G 完整闭环
- 风险：样本通过但全量性能/边界问题暴露
- 回归影响：高
- 推荐顺序：Gate E 后再执行
