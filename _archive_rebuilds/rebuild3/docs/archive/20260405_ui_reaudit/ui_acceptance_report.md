# UI 页面验收报告

## 结论

本轮 UI-first 重构已完成正式页面体系与主导航对齐，当前主工作台覆盖 13 个正式前端页面，启动器已切回独立 Python 入口。

当前验收结果：

- 独立启动器 UI / API：通过（`launcher.py` + `/api/launcher/*`）
- 前端构建：通过（`npm run build`）
- 后端语法校验：通过（`python3 -m py_compile ...`）
- 后端接口 smoke test：通过（临时 TestClient 环境）
- 页面壳层 / 导航 / 版本上下文：通过
- 主流程页：已接正式读模型
- 支撑治理页中的 `/compare`、`/governance`：保留显式 fallback 标记

## 页面清单

| 页面 | 路由 | API | 数据来源 | 当前状态 | 可接受差异 |
|---|---|---|---|---|---|
| 启动器 | `http://127.0.0.1:47120` | `/api/launcher/services` `/api/launcher/logs/{service}` `/api/launcher/services/{service}/{action}` | 本地端口 / pid / log 文件 | 通过 | 独立 Python 启动器；backend/frontend 支持 start/stop/restart/kill-port；database 只做状态检查 |
| 流转总览 | `/flow/overview` | `/api/v1/runs/current` `/flow-overview` `/flow-snapshots` | `rebuild3_meta.*` + `rebuild3_sample_meta.*` | 通过 | delta 当前以 sample validation 作为对照基准 |
| 运行 / 批次中心 | `/runs` | `/api/v1/runs/batches` `/batch/{id}` | `batch` / `batch_snapshot` / `batch_anomaly_summary` | 通过 | 当前只有 sample + full 两个结构化批次，趋势为结构对照而非长期趋势 |
| 对象浏览 | `/objects` | `/api/v1/objects/summary` `/list` | `rebuild3.obj_*` + `stg_*` + `r2_full_*` | 通过 | 采用统一主表格表达，未做虚拟滚动 |
| 对象详情 | `/objects/:objectType/:objectId` | `/api/v1/objects/detail` | `obj_*` / `obj_state_history` / `fact_*` / `r2_full_*` | 通过 | 历史面板为列表式，不是图形时间线 |
| 等待 / 观察工作台 | `/observation` | `/api/v1/runs/observation-workspace` | `rebuild3.obj_cell` + 派生资格进度 | 通过 | 趋势为派生接近度，不是真实多批斜率 |
| 异常工作台 | `/anomalies` | `/api/v1/runs/anomaly-workspace` | `obj_cell` / `obj_bs` / `fact_*` / `batch_anomaly_summary` | 通过 | 对象级/记录级已拆双视角，未做更细 sub-tab |
| 基线 / 画像 | `/baseline` | `/api/v1/runs/baseline-profile` | `baseline_*` / `baseline_version` / `r2_full_*` | 通过 | 稳定性分数为页面启发式提示，非后端正式评分 |
| 验证 / 对照 | `/compare` | `/api/v1/compare/overview` `/diffs` | `sample_compare_report.md` + `full_compare_report.md` fallback | 通过 | 明确标注 `report_fallback` |
| LAC 画像 | `/profiles/lac` | `/api/v1/objects/profile-list?object_type=lac` | `obj_lac` + `stg_lac_profile` + `r2_full_lac_*` | 通过 | 区域标签作为质量列，旧标签仅解释层 |
| BS 画像 | `/profiles/bs` | `/api/v1/objects/profile-list?object_type=bs` | `obj_bs` + `stg_bs_profile` + `r2_full_bs_*` | 通过 | `classification_v2` 仅解释层文本展示 |
| Cell 画像 | `/profiles/cell` | `/api/v1/objects/profile-list?object_type=cell` | `obj_cell` + `stg_cell_profile` + `r2_full_cell_*` | 通过 | 以统一画像表格替代旧 spike 单页结构 |
| 初始化数据 | `/initialization` | `/api/v1/runs/initialization` | `rebuild3_sample_meta.*` | 通过 | 目前只显示 sample initialization 结果 |
| 基础数据治理 | `/governance` | `/api/v1/governance/*` | fallback catalog | 通过 | 明确标注 `fallback_catalog`，实际使用仅部分表已录入 |

## 主流程读模型状态

### 已接真实读模型

- `runs/*`
- `objects/*`
- `launcher.py` 独立状态接口

### 已接真实表 + 局部派生

- `/observation`
- `/anomalies`
- `/baseline`
- `/initialization`

### 显式 fallback

- `/compare`
- `/governance`

## 构建与校验记录

### 已完成

```bash
cd rebuild3/frontend && npm run build
python3 -m py_compile rebuild3/launcher/launcher.py
python3 -m py_compile rebuild3/backend/app/api/*.py rebuild3/backend/app/core/*.py rebuild3/backend/app/main.py
source /tmp/rebuild3_check_env/bin/activate
PYTHONPATH=rebuild3/backend python - <<'PY'
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
client.get('/api/v1/health')
client.get('/api/v1/runs/current')
client.get('/api/v1/runs/flow-overview')
client.get('/api/v1/runs/batches')
client.get('/api/v1/runs/observation-workspace')
client.get('/api/v1/runs/anomaly-workspace')
client.get('/api/v1/runs/baseline-profile')
client.get('/api/v1/runs/initialization')
client.get('/api/v1/objects/summary', params={'object_type': 'cell'})
client.get('/api/v1/objects/list', params={'object_type': 'cell', 'page': 1, 'page_size': 10})
client.get('/api/v1/objects/profile-list', params={'object_type': 'cell', 'page': 1, 'page_size': 10})
client.get('/api/v1/compare/overview')
client.get('/api/v1/compare/diffs')
client.get('/api/v1/governance/overview')
client.get('/api/v1/governance/tables')
PY
python3 rebuild3/launcher/launcher.py --host 127.0.0.1 --port 47120
curl http://127.0.0.1:47120/api/launcher/services
```

### 备注

- 本机默认 `python3` 环境仍缺少 `fastapi`
- 本轮 smoke test 使用临时虚拟环境 `/tmp/rebuild3_check_env`
- 正式启动脚本仍优先读取 `rebuild3/.venv`
- 独立启动器 `rebuild3/launcher/launcher.py` 使用 Python 标准库实现，不依赖 FastAPI

## 最终结论

当前正式实现满足 Prompt F 对“UI 是首要验收对象”的要求：

- 页面边界与 UI_v2 主导航一致
- 主流程链路已可见、可构建、可接数
- fallback 页面已显式标记
- 独立启动器与本地启动说明已补齐
