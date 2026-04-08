# 归档执行报告

## 1. 执行时点

本次归档在以下条件满足后执行：

- 正式 UI 页面体系已落地
- 前端构建通过
- 启动脚本与运行说明已补齐
- spike 替代关系已明确

## 2. 已归档文件

### frontend spike

已保留在 `rebuild3/archive/20260404_ui_spike/frontend_spike/`：

- 旧 `App.vue`
- 旧 `main.ts`
- 旧 `router.ts`
- 旧 `styles.css`
- 旧 `format.ts`
- 旧 `cellApi.ts`
- 旧 `BadgePill.vue`
- 旧 `MetricBars.vue`
- 旧 `QualificationStrip.vue`
- 旧 `CellObjectsPage.vue`
- 旧 `CellDetailPage.vue`
- 旧 `CellProfilePage.vue`

### backend spike

已保留在 `rebuild3/archive/20260404_ui_spike/backend_spike/`：

- `object_api_v1.py`

### launcher placeholder

已保留在 `rebuild3/archive/20260404_ui_spike/launcher_placeholder/`：

- 旧 `launcher/README.md`

## 3. 已从正式实现路径移除的 spike 文件

已删除以下旧前端活动文件，避免与正式页面并存：

- `rebuild3/frontend/src/lib/cellApi.ts`
- `rebuild3/frontend/src/components/MetricBars.vue`
- `rebuild3/frontend/src/pages/CellObjectsPage.vue`
- `rebuild3/frontend/src/pages/CellDetailPage.vue`
- `rebuild3/frontend/src/pages/CellProfilePage.vue`

## 4. 正式替代实现位置

### 前端

- `rebuild3/frontend/src/App.vue`
- `rebuild3/frontend/src/router.ts`
- `rebuild3/frontend/src/pages/*.vue`（14 个正式页面）

### 后端

- `rebuild3/backend/app/api/run.py`
- `rebuild3/backend/app/api/object.py`
- `rebuild3/backend/app/api/compare.py`
- `rebuild3/backend/app/api/governance.py`
- `rebuild3/backend/app/api/launcher.py`

### 运行入口

- `rebuild3/scripts/dev/*.sh`
- `rebuild3/docs/runtime_startup_guide.md`

## 5. 生成产物处理

以下产物不做历史归档：

- `frontend/dist/`
- `backend/**/__pycache__/`

本轮处理方式：

- `frontend/dist/`：已在构建验证后清理
- `backend/**/__pycache__/`：已清理
- `frontend/node_modules/`：保留为本地依赖目录，不进入 archive

## 6. 结论

本次归档已经把“2026-04-04 UI spike”从正式实现路径中移除，只保留为历史参考，目录角色已重新明确。
