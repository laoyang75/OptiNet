# rebuild3

rebuild3 当前已经切换到 UI-first 的正式交付路径：

- 正式前端：Vue 3 + TypeScript + Vite
- 正式后端：FastAPI + psycopg
- 正式启动器：独立 Python Web Launcher

## 当前状态

- Gate A0 / A1 / B：已完成（目录审计、页面映射、UI-first 任务书）
- 主工作台页面：13 个正式前端路由
- 独立启动器：已迁回 `rebuild3/launcher/launcher.py`
- 主流程读模型：已完成并接入主页面
- compare / governance：保留显式 fallback
- UI spike 归档：已执行

## 目录说明

- `docs/`：冻结文档、实施文档、运行说明、验收报告、归档报告
- `backend/`：FastAPI 读模型、SQL、脚本
- `frontend/`：正式前端工程
- `launcher/`：独立 Python 启动器与静态 UI
- `scripts/dev/`：本地启动 / 停止 / 状态脚本
- `runtime/`：pid / log 运行时目录
- `archive/20260404_ui_spike/`：上一轮跑偏 spike 归档

## 快速开始

### 1. 后端依赖

```bash
python3 -m venv rebuild3/.venv
source rebuild3/.venv/bin/activate
pip install -r rebuild3/backend/requirements.txt
```

### 2. 前端依赖

```bash
cd rebuild3/frontend
npm install
```

### 3. 先启动独立启动器

```bash
./rebuild3/scripts/dev/start_launcher.sh
```

### 4. 在启动器中启动后端 / 前端，或直接用脚本

```bash
./rebuild3/scripts/dev/start_all.sh
```

### 5. 检查状态

```bash
./rebuild3/scripts/dev/status.sh
```

## 默认访问地址

- 启动器：`http://127.0.0.1:47120`
- 后端：`http://127.0.0.1:47121`
- 前端工作台：`http://127.0.0.1:47122`
- 后端健康检查：`http://127.0.0.1:47121/api/v1/health`

## 关键说明

- 端口已从常见的 `8000 / 5173` 迁移到较不易冲突的 `47121 / 47122`，启动器使用 `47120`
- baseline 原则：当前批次只读取上一版冻结 baseline
- 主流程页连接正式读模型
- `/compare` 与 `/governance` 当前仍为显式 fallback 页面
- 详细启动说明见 `rebuild3/docs/runtime_startup_guide.md`
