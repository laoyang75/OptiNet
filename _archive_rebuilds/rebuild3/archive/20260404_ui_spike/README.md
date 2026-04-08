# 2026-04-04 UI spike 归档说明

- 归档日期：2026-04-05
- 归档原因：上一轮实现把前端做成了 Cell-only spike，偏离了 `UI_v2` 的正式页面体系和启动器要求
- 替代版本：本轮 UI-first 正式实现（`rebuild3/frontend/src` 当前主干 + `rebuild3/backend/app/api` 正式读模型）
- 参考价值：保留作为“跑偏实现”和“字段表达早期探索”的历史对照，不再参与正式运行路径

## 归档内容

- `frontend_spike/`：旧 App Shell、旧 Cell 页面、旧局部组件、旧 `cellApi.ts`
- `backend_spike/`：旧 `object.py` 版本
- `launcher_placeholder/`：旧 `launcher/README.md` 占位说明

## 说明

1. 正式实现已经接管以下角色：
   - 三组侧边栏导航
   - 14 个正式页面路由
   - 对象统一读模型
   - 启动器与脚本化本地运行入口
2. 归档内容仅供回溯，不应再复制回主实现目录。
