# rebuild3 本地启动说明

## 1. 目标

本轮交付的本地运行入口由两部分组成：

- 独立启动器：`rebuild3/launcher/launcher.py`
- 脚本入口：`rebuild3/scripts/dev/*.sh`

推荐顺序：先启动独立启动器，再从启动器里拉起前端和后端。

---

## 2. 默认端口

为避免与本机常见开发服务冲突，本轮统一改为以下高位端口：

- 启动器：`47120`
- 后端：`47121`
- 前端：`47122`

如需覆盖，可设置环境变量：

- `REBUILD3_LAUNCHER_HOST` / `REBUILD3_LAUNCHER_PORT`
- `REBUILD3_BACKEND_HOST` / `REBUILD3_BACKEND_PORT`
- `REBUILD3_FRONTEND_HOST` / `REBUILD3_FRONTEND_PORT`

---

## 3. 依赖准备

### Python / backend / launcher

建议在 `rebuild3/.venv` 中安装后端依赖：

```bash
python3 -m venv rebuild3/.venv
source rebuild3/.venv/bin/activate
pip install -r rebuild3/backend/requirements.txt
```

说明：

- 启动脚本会优先使用 `rebuild3/.venv/bin/python`
- 如果未创建虚拟环境，则回退到系统 `python3`
- 启动器本身只使用 Python 标准库，不额外依赖 FastAPI
- 默认数据库连接：`postgresql://postgres:123456@192.168.200.217:5433/ip_loc2`
- 如需覆盖，可设置：`REBUILD3_PG_DSN`、`REBUILD3_PG_HOST`、`REBUILD3_PG_PORT`

### Node / frontend

```bash
cd rebuild3/frontend
npm install
```

---

## 4. 启动方式

### 先启动独立启动器

```bash
./rebuild3/scripts/dev/start_launcher.sh
```

如不希望自动打开浏览器，可临时执行：

```bash
REBUILD3_LAUNCHER_OPEN_BROWSER=0 ./rebuild3/scripts/dev/start_launcher.sh
```

### 在启动器里启动服务

启动器打开后，可直接操作：

- 启动后端
- 启动前端
- 批量 start / stop / restart
- 查看最近日志
- 必要时处理端口冲突

### 纯脚本方式

```bash
./rebuild3/scripts/dev/start_all.sh
./rebuild3/scripts/dev/stop_all.sh
./rebuild3/scripts/dev/status.sh
```

### 单服务脚本

```bash
./rebuild3/scripts/dev/start_backend.sh
./rebuild3/scripts/dev/stop_backend.sh
./rebuild3/scripts/dev/restart_backend.sh
./rebuild3/scripts/dev/start_frontend.sh
./rebuild3/scripts/dev/stop_frontend.sh
./rebuild3/scripts/dev/restart_frontend.sh
./rebuild3/scripts/dev/stop_launcher.sh
./rebuild3/scripts/dev/restart_launcher.sh
```

---

## 5. 访问地址

启动成功后：

- 启动器：`http://127.0.0.1:47120`
- 前端工作台：`http://127.0.0.1:47122`
- 后端健康检查：`http://127.0.0.1:47121/api/v1/health`

---

## 6. 日志与 PID

脚本会在 `rebuild3/runtime/` 下维护：

- `launcher.pid`
- `launcher.log`
- `backend.pid`
- `backend.log`
- `frontend.pid`
- `frontend.log`

独立启动器会读取这些文件并显示最近日志。

---

## 7. 当前实现边界

### 启动器内可直接控制的服务

- `backend`：支持 `start / stop / restart / kill-port`
- `frontend`：支持 `start / stop / restart / kill-port`

### 启动器内只做状态检查的服务

- `database`：只检查连通性，不在应用内执行 start/stop

因此：

- 首次使用建议先启动 `start_launcher.sh`
- 如需无 UI 脚本化启动，可直接执行 `start_all.sh`

---

## 8. 启动成功判定

至少满足以下条件：

1. `./rebuild3/scripts/dev/status.sh` 显示 `launcher=running`
2. `http://127.0.0.1:47120` 能看到 UI_v2 风格的启动器卡片与日志区
3. `http://127.0.0.1:47121/api/v1/health` 返回 `status=ok`
4. `http://127.0.0.1:47122` 能进入主工作台

补充说明：

- 如果 `status.sh` 显示 `port-open`，表示端口已被其他进程占用，但不是由 `rebuild3/runtime/*.pid` 管理的实例
- 此时不要直接判定启动成功，应先处理端口冲突，再重新执行启动脚本

---

## 9. 常见问题

### launcher 启动失败

优先检查：

- `47120` 端口是否已被占用
- `rebuild3/runtime/launcher.log`
- 当前 `python3` 是否可正常启动标准库 HTTP 服务

### backend 启动失败

优先检查：

- 是否已安装 `fastapi / uvicorn / psycopg`
- 数据库地址是否可达
- `rebuild3/runtime/backend.log`

### frontend 启动失败

优先检查：

- 是否执行过 `npm install`
- `47122` 端口是否被占用
- `rebuild3/runtime/frontend.log`

### `status.sh` 显示 `port-open`

表示：

- 端口存在监听
- 但当前 `runtime/*.pid` 中没有对应存活进程

建议处理：

- 先确认占用端口的是否为本项目实例
- 若不是，先释放对应端口，再重新执行启动脚本
- 也可以直接在独立启动器里点击 `kill-port`

### 页面显示但部分模块是 fallback

当前允许且已显式标注的 fallback：

- `/compare`：基于报告回退
- `/governance`：基于 fallback catalog 回退

其余主流程页均连接正式读模型接口。
