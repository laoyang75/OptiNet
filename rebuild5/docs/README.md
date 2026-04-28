# Rebuild5 文档导航

> 更新声明(2026-04-28)
> - 当前生产环境: PG 18.3 / Citus 14.0-1 / PostGIS 3.6.3 / coordinator `192.168.200.217:5488` / database `yangca`
> - 本文件只承担导航职责;业务规则、状态机、术语和操作细节分别以下层权威文档为准

## 1. 先看这 6 份权威文档

| 文档 | 用途 |
|---|---|
| [`PROJECT_STATUS.md`](./PROJECT_STATUS.md) | 当前状态、历史阶段索引、回归基线 |
| [`CLUSTER_USAGE.md`](./CLUSTER_USAGE.md) | 集群使用原则、Citus 兼容边界、环境禁忌 |
| [`runbook.md`](./runbook.md) | 日常跑批、验证、升级/维护入口 |
| [`处理流程总览.md`](./处理流程总览.md) | Step1-5 状态机总线 |
| [`术语对照表.md`](./术语对照表.md) | UI/文档/代码术语统一口径 |
| [`00_全局约定.md`](./00_全局约定.md) | 字段命名、状态定义、全局边界 |

## 2. 推荐阅读顺序

1. [`处理流程总览.md`](./处理流程总览.md) — 先建立 Step1-5 的状态机边界。
2. [`00_全局约定.md`](./00_全局约定.md) — 再看字段、状态和全局约束。
3. [`术语对照表.md`](./术语对照表.md) — 避免把内部术语和 UI 表达混用。
4. [`PROJECT_STATUS.md`](./PROJECT_STATUS.md) — 对齐当前环境、基线和历史阶段。
5. [`CLUSTER_USAGE.md`](./CLUSTER_USAGE.md) — 写 SQL / 改代码前必须读。
6. [`runbook.md`](./runbook.md) — 真正开始跑批或验证时再读。

## 3. 13 篇核心开发文档

| 文档 | 主题 |
|---|---|
| [`00_全局约定.md`](./00_全局约定.md) | 系统级约定 |
| [`01a_数据源接入_功能要求.md`](./01a_数据源接入_功能要求.md) | Step1 功能要求 |
| [`01b_数据源接入_处理规则.md`](./01b_数据源接入_处理规则.md) | Step1 处理规则 |
| [`02_基础画像.md`](./02_基础画像.md) | Step2 分流与基础画像 |
| [`03_流式质量评估.md`](./03_流式质量评估.md) | Step3 生命周期评估 |
| [`04_知识补数.md`](./04_知识补数.md) | Step4 补数 |
| [`05_画像维护.md`](./05_画像维护.md) | Step5 维护 / 多质心 / 碰撞 |
| [`06_服务层_运营商数据库与分析服务.md`](./06_服务层_运营商数据库与分析服务.md) | Step6 查询消费层 |
| [`07_数据集选择与运行管理.md`](./07_数据集选择与运行管理.md) | 数据集与运行管理 |
| [`08_UI设计.md`](./08_UI设计.md) | UI 设计总纲 |
| [`09_控制操作_初始化重算与回归.md`](./09_控制操作_初始化重算与回归.md) | 重跑与回归控制 |
| [`10_调试期结果保留与字段口径提示.md`](./10_调试期结果保留与字段口径提示.md) | 调试期口径提示 |
| [`11_核心表说明.md`](./11_核心表说明.md) | 核心表与 schema 口径 |

## 4. 当前 active 区域

| 路径 | 说明 |
|---|---|
| [`gps1/`](./gps1/) | 2026-04-28 启动的新分析周期工作区 |
| [`PROJECT_STATUS.md`](./PROJECT_STATUS.md) | 当前项目状态总览 |
| [`runbook.md`](./runbook.md) | 当前操作入口 |

## 5. 历史 trail

所有历史修复、升级、交付和旧 prompt 已统一归档到 [`archive/`](./archive/)。

| 路径 | 说明 |
|---|---|
| [`archive/fix_history/`](./archive/fix_history/) | `fix` / `fix1-5` / `fix6_optim` / `loop_optim` / `upgrade` |
| [`archive/delivery_reports/`](./archive/delivery_reports/) | 历史交付报告 |
| [`archive/old_prompts/`](./archive/old_prompts/) | 老 prompt / 老 runbook |
| [`archive/dev/`](./archive/dev/) | 开发期调试笔记 |
| [`archive/human_guide/`](./archive/human_guide/) | 老操作指南 |
| [`archive/gps研究/`](./archive/gps研究/) | 老 GPS 研究目录 |

## 6. 快速判断

| 你要做的事 | 先看哪里 |
|---|---|
| 跑批 / 验证 / reset | [`runbook.md`](./runbook.md) |
| 改 SQL / 改分布式写入逻辑 | [`CLUSTER_USAGE.md`](./CLUSTER_USAGE.md) |
| 理解主链状态机 | [`处理流程总览.md`](./处理流程总览.md) |
| 查字段或核心表 | [`00_全局约定.md`](./00_全局约定.md) + [`11_核心表说明.md`](./11_核心表说明.md) |
| 查历史为什么这么设计 | [`PROJECT_STATUS.md`](./PROJECT_STATUS.md) + [`archive/fix_history/`](./archive/fix_history/) |
| 开启新研究周期 | [`gps1/README.md`](./gps1/README.md) |

## 7. 现在不要做的事

- 不要把新文档继续塞回 `fix5/ fix6_optim/ loop_optim/ upgrade` 这类历史目录;它们已经冻结到 `archive/`。
- 不要把 `archive/` 当成当前权威文档源;当前口径以前 6 份权威文档和 13 篇核心开发文档为准。
- 不要根据旧 `runbook_v5.md`、旧 prompt 或 PG17/5433 时代说明直接操作当前生产环境。
