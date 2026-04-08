# 启动器页面设计说明

## 页面目标

帮助运维人员管理 rebuild3 系统的所有服务进程。该页面独立于主系统运行，是一个轻量级运维控制面板，用于启停服务、监控运行状态、查看实时日志。

## 用户主要操作

1. 查看所有服务运行状态（后端 API / 前端开发服务 / 数据库）
2. 启动 / 停止 / 重启单个服务
3. 一键管理全部服务（批量启动、停止、重启）
4. 查看实时日志输出，按级别筛选
5. 强制杀掉卡死端口（危险操作，单独标记）

## 页面区块说明

| 区块名称 | 面积占比 | 核心作用 | 核心字段 |
|---------|---------|---------|---------|
| Header | 5% | 展示页面标题、当前时间、系统整体健康状态 | 标题、时间戳、运行服务数 |
| 全局控制栏 | 5% | 批量操作全部服务 | 一键启动/停止/重启按钮 |
| 服务卡片列表 | 45% | 展示每个服务的详细状态，提供单服务操作入口 | 服务名、类型、状态徽标、PID、端口、运行时间、操作按钮 |
| 日志查看器 | 45% | 查看选定服务的实时日志输出 | Tab 切换、级别筛选、日志内容、自动滚动 |

## 筛选器 & 排序

### 日志级别筛选

- **ALL** — 显示全部日志（默认）
- **INFO** — 仅显示一般信息
- **WARN** — 仅显示警告
- **ERROR** — 仅显示错误

筛选按钮位于日志区域工具栏左侧，选中状态使用 Indigo-500 高亮。服务切换通过 Tab 栏实现，点击切换不同服务的日志流。

## 状态表达规则

| 状态 | 英文标识 | 颜色 | 视觉表达 |
|------|---------|------|---------|
| 运行中 | Running | Green-500 (#22c55e) | 绿色圆点 + 脉冲动画 + 浅绿背景徽标 |
| 已停止 | Stopped | Red-500 (#ef4444) | 红色圆点（静止） + 浅红背景徽标 |
| 启动中 | Starting | Amber-500 (#f59e0b) | 琥珀色圆点 + 闪烁动画 + 浅黄背景徽标 |
| 错误 | Error | Red-600 (#dc2626) | 深红圆点（静止） + 浅红背景徽标 |

运行中状态的圆点使用 `pulse` CSS 动画，周期 2 秒，提供呼吸灯效果。启动中状态使用更快的闪烁节奏（1.5 秒），表达"正在进行"。

## 组件边界建议

实际开发使用 Vue 3 + TypeScript，建议拆分为以下组件：

```
LauncherPage.vue              ← 页面根组件
├── LauncherHeader.vue        ← 标题、时间、系统状态汇总
├── GlobalControls.vue        ← 全局一键操作按钮组
├── ServiceCardList.vue       ← 服务卡片列表容器
│   └── ServiceCard.vue       ← 单个服务卡片（props: service 对象）
│       └── StatusBadge.vue   ← 状态徽标（props: status 枚举）
└── LogViewer.vue             ← 日志查看器
    ├── LogTabs.vue           ← 服务 Tab 切换
    ├── LogToolbar.vue        ← 级别筛选 + 清空按钮
    └── LogContent.vue        ← 日志内容区域（虚拟滚动）
```

核心类型定义：

```typescript
type ServiceStatus = 'running' | 'stopped' | 'starting' | 'error'

interface ServiceInfo {
  id: string
  name: string          // "后端 API"
  type: string          // "FastAPI"
  port: number
  pid: number | null
  status: ServiceStatus
  uptime: string | null // "2小时 15分"
}

type LogLevel = 'INFO' | 'WARN' | 'ERROR'

interface LogEntry {
  timestamp: string
  level: LogLevel
  message: string
  service: string
}
```

## 读模型建议

启动器需要以下后端接口：

| 接口 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 获取所有服务状态 | GET | `/launcher/services` | 返回 `ServiceInfo[]` |
| 启动服务 | POST | `/launcher/services/{id}/start` | 启动指定服务 |
| 停止服务 | POST | `/launcher/services/{id}/stop` | 优雅停止 |
| 重启服务 | POST | `/launcher/services/{id}/restart` | 先停后启 |
| 杀掉端口 | POST | `/launcher/services/{id}/kill-port` | 强制 kill -9 |
| 批量操作 | POST | `/launcher/services/batch` | body: `{ action: 'start' \| 'stop' \| 'restart' }` |
| 日志流 | WebSocket | `/launcher/logs/{service_id}` | 实时推送日志 |

轮询策略：服务状态每 3 秒轮询一次（或使用 SSE 推送）。日志通过 WebSocket 实时推送，无需轮询。

## 空状态 / 错误状态

| 场景 | 处理方式 |
|------|---------|
| 所有服务未启动 | 服务卡片全部显示"已停止"，Header 状态变为 "0/3 服务运行中"，全局只高亮"一键启动"按钮 |
| 单个服务启动失败 | 该卡片状态切换为 Error，自动切换日志 Tab 到该服务并滚动到最新错误行 |
| 启动器后端不可达 | 页面顶部显示红色全宽 banner："启动器后端连接失败，请检查进程"，所有操作按钮禁用 |
| 日志为空 | 日志区域居中显示灰色文字 "暂无日志" |
| PID 不存在（进程意外退出）| 状态自动标记为 Error，PID 显示为 "—" |
| 端口被其他进程占用 | 启动失败后提示端口冲突，引导用户使用"杀掉端口"按钮 |

## 开发注意事项

1. **WebSocket 日志推送** — 使用 WebSocket 连接实时接收日志。前端需处理断线重连（指数退避），连接状态在日志区域底部提示。
2. **进程管理安全** — "杀掉端口"按钮执行的是 `kill -9`，属于危险操作。UI 上使用红色虚线边框标记，点击后必须弹出二次确认对话框。
3. **并发保护** — 操作按钮点击后应立即禁用，防止重复提交。状态切换到 "启动中" 后解锁需等后端确认。
4. **日志性能** — 日志区域应使用虚拟滚动（如 `vue-virtual-scroller`），避免 DOM 节点过多。保留最近 5000 条日志，超出后自动丢弃旧条目。
5. **独立部署** — 启动器不依赖主系统的前端和后端，独立运行在单独端口（如 9000），避免"需要先启动系统才能用启动器"的循环依赖。
6. **权限控制** — 生产环境应添加基础认证（Basic Auth 或 Token），防止误操作。开发环境可跳过。
7. **响应式** — 面板主要在桌面浏览器使用，最小支持宽度 768px，无需移动端适配。
