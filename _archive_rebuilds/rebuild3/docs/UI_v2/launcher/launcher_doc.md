# 启动器 设计说明

## 页面目标

独立运维控制面板，管理 rebuild3 系统进程的启动、停止、重启和日志查看。

启动器是用户进入 rebuild3 的第一步（见 design_notes.md 日常使用主链路），在打开流转总览之前先确认所有服务正常运行。它不参与主工作台的导航体系，是一个独立的运维入口。

## 这个页面主要回答什么问题

- 各服务是否正在运行
- 进程 PID 和端口是否正确
- 是否有错误日志需要关注

## 用户主要操作

1. 查看各服务运行状态
2. 启动/停止/重启单个服务
3. 一键操作全部服务
4. 查看和过滤服务日志
5. 强制杀掉端口（紧急操作）

## 页面区块说明

| 区块名称 | 面积占比 | 核心作用 | 必须字段 | 是否需要 delta | 是否支持下钻 |
|---------|---------|---------|---------|---------------|-------------|
| 顶部操作栏 | 8% | 全局批量操作 | — | 否 | 否 |
| 服务卡片区 | 35% | 各服务状态与控制 | 服务名/状态/PID/端口/时长 | 否 | 否 |
| 日志查看区 | 57% | 实时日志与过滤 | 时间/级别/内容 | 否 | 否 |

## 筛选器与切换器

- 服务 tab 切换（后端 API / 前端 / 数据库）
- 日志级别过滤（ALL / INFO / WARN / ERROR）

## 状态表达规则

| 状态 | 视觉表达 | CSS 实现 |
|------|---------|---------|
| 运行中 (Running) | 绿色脉冲圆点 + 绿色底徽标 | `status-running` + `pulse-green` animation |
| 已停止 (Stopped) | 红色实心圆点 + 红色底徽标 | `status-stopped` |
| 启动中 (Starting) | 黄色闪烁圆点 + 黄色底徽标 | `status-starting` + `pulse-amber` animation |
| 错误 | 红色实心圆点 + 红色图标 + 卡片内错误信息 | 复用 `status-stopped` 样式 + 错误文字 |

## 下钻路径

无（独立页面，不参与主工作台导航）

## 组件边界建议

```
launcher/
├── LauncherPage.vue          # 页面容器，组合以下子组件
├── ServiceCard.vue           # 单服务卡片（状态/元数据/操作按钮）
├── LogViewer.vue             # 日志查看区容器（工具栏 + 内容区）
└── LogFilter.vue             # 日志过滤器（tab 切换 + 级别过滤 + 自动滚动开关）
```

### Props 设计

**ServiceCard.vue**
```ts
interface ServiceCardProps {
  name: string            // 显示名称，如 "后端 API"
  tech: string            // 技术栈，如 "FastAPI · Python"
  port: number            // 端口号
  status: 'running' | 'stopped' | 'starting' | 'error'
  pid: number | null      // 进程 ID，停止时为 null
  uptime: string | null   // 运行时长，停止时为 null
}
```

**LogViewer.vue**
```ts
interface LogLine {
  ts: string              // ISO 时间戳
  level: 'info' | 'warn' | 'error'
  msg: string             // 日志内容
}

interface LogViewerProps {
  services: string[]      // tab 列表
  activeService: string   // 当前选中的服务
  lines: LogLine[]        // 当前服务的日志行
}
```

## 读模型建议

### 实时通信

- WebSocket `/ws/launcher/status` — 推送服务状态变更（启动/停止/PID 变化/uptime 更新）
- WebSocket `/ws/launcher/logs/:service` — 推送指定服务的实时日志行

### REST API

```
GET  /api/launcher/services
→ [{ name, tech, port, status, pid, uptime }]

POST /api/launcher/services/:name/start
POST /api/launcher/services/:name/stop
POST /api/launcher/services/:name/restart
POST /api/launcher/services/:name/kill-port

POST /api/launcher/services/all/start
POST /api/launcher/services/all/stop
POST /api/launcher/services/all/restart
```

## 空状态 / 错误状态 / 重跑中状态

| 场景 | 表现 |
|------|------|
| 服务列表为空 | 卡片区显示空状态插画 + "未配置任何服务" |
| 服务控制失败 | 对应卡片底部显示红色错误信息条，3 秒后自动消失或手动关闭 |
| WebSocket 断开 | 顶部显示黄色警告条："实时连接已断开，正在重连..." |
| 日志为空 | 日志区显示灰色文字 "暂无日志" |
| 杀掉端口确认 | 弹出确认对话框，需用户二次确认 |

## 开发注意事项

1. **独立启动** — 启动器通过独立 Python 脚本启动（不依赖主系统前后端），是用户进入 rebuild3 的第一步
2. **危险操作保护** — "杀掉端口"使用红色虚线边框标识危险性，点击后必须弹出二次确认
3. **实时推送** — 日志使用 WebSocket 实时推送，断开后自动重连（指数退避，最大间隔 30 秒）
4. **样式一致性** — 使用与主系统相同的 CSS custom properties（indigo 主色、圆角、阴影层级），但页面更简洁，偏运维风格
5. **日志性能** — 日志区需限制最大行数（建议 2000 行），超出后自动移除最早的行，避免 DOM 节点过多导致卡顿
6. **自动滚动** — 默认开启自动滚动到最新日志；用户手动上滚时自动暂停，切换回最新时恢复
