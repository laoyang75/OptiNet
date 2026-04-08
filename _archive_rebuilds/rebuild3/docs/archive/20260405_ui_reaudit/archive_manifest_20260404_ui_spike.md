# 归档清单：2026-04-04 UI spike

> 目的：列出本轮跑偏实现中，**在新 UI-first 正式实现通过验收后** 应归档或清理的文件，避免后续目录混乱。

## 1. 归档执行前提

只有同时满足以下条件，才允许执行归档：

1. 新一轮 `UI_v2` 对齐实现已经通过页面级验收
2. 用户可以通过正式启动入口独立运行系统
3. 对应替代文件已经稳定存在
4. 已输出归档执行报告

在此之前，本清单中的文件都应保留为参考，不得提前删除。

---

## 2. 建议归档的 spike 文件（前端）

这些文件属于本轮“独立原型式 UI spike”，如果下一轮正式实现已经替代它们，应整体归档：

- `rebuild3/frontend/src/App.vue`
- `rebuild3/frontend/src/main.ts`
- `rebuild3/frontend/src/router.ts`
- `rebuild3/frontend/src/styles.css`
- `rebuild3/frontend/src/lib/cellApi.ts`
- `rebuild3/frontend/src/lib/format.ts`
- `rebuild3/frontend/src/components/BadgePill.vue`
- `rebuild3/frontend/src/components/MetricBars.vue`
- `rebuild3/frontend/src/components/QualificationStrip.vue`
- `rebuild3/frontend/src/pages/CellObjectsPage.vue`
- `rebuild3/frontend/src/pages/CellDetailPage.vue`
- `rebuild3/frontend/src/pages/CellProfilePage.vue`

归档原因：

- 这些文件没有沿用 `UI_v2` 全量页面体系
- 它们更像局部 Cell 工作台 spike，而不是正式系统前端
- 继续与正式实现并存会造成目录和认知混乱

---

## 3. 条件归档的 spike 文件（后端）

这些文件不一定全部归档，但如果下一轮正式读模型/API 重建后已完全替代，应将旧版本归档：

- `rebuild3/backend/app/api/object.py`

处理原则：

1. 如果新正式实现直接吸收并保留其结构，则不归档，只保留演进后的正式文件
2. 如果新正式实现重写了对象读模型，则应把当前版本复制到归档目录，作为“2026-04-04 spike 参考实现”保留

---

## 4. 不做历史归档、只做清理/重建的生成产物

以下内容属于可再生构建产物，不建议作为历史档案保留：

- `rebuild3/frontend/dist/`
- `rebuild3/frontend/node_modules/`
- `rebuild3/frontend/node_modules/.vite/`
- `rebuild3/frontend/node_modules/.vite-temp/`

处理原则：

- 不放入 archive
- 通过重建、清理、忽略规则处理
- 如需记录，只在归档执行报告中注明“已清理/已重建”

---

## 5. 建议归档目录结构

建议在正式替代实现验收通过后，将归档内容移动到：

```text
rebuild3/archive/20260404_ui_spike/
├── README.md
├── frontend_spike/
│   └── ...
└── backend_spike/
    └── ...
```

其中 `README.md` 至少应写明：

- 归档日期
- 归档原因
- 原始任务偏差说明
- 被哪一轮正式实现替代
- 是否仍有参考价值

---

## 6. 归档执行报告

归档完成后，必须输出：

- `rebuild3/docs/archive_execution_report.md`

报告至少包含：

1. 实际归档了哪些文件
2. 哪些文件未归档以及原因
3. 哪些生成产物被清理/重建
4. 正式替代实现位于哪里

