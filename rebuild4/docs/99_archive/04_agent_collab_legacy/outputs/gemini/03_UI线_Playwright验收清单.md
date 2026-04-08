# UI 线 Playwright 验收清单（Gemini 草案）

状态：可合并草案  
更新时间：2026-04-06

## 1. 总要求

所有涉及页面交付的步骤，都必须包含 Playwright 验收。  
Playwright 不是可选附加项，而是 Gate 通过条件的一部分。

## 2. 通用断言

每个页面都至少断言：

1. 页面可打开
2. 主标题与主语上下文可见
3. `data_origin` 可见
4. 核心主体区域非空，或 honest empty 正确显示
5. 关键 CTA / drill-down 可点击

## 3. 页面级清单

### 3.1 `/runs`

断言：
- 列表区存在
- 至少 1 个 run 卡片或行
- 点击某个 run 后，详情区更新
- 当前选中 run/batch 的 `data_origin` 可见

### 3.2 `/flow/overview`

断言：
- 批次上下文条可见
- 流程节点区域可见
- 四分流摘要可见
- 若为 synthetic，banner 明显可见

### 3.3 `/flow/snapshot`

断言：
- 时间点或阶段选择器可见
- 切换时间点后至少一处数字或表格变化
- 主语仍指向 batch + snapshot
- 无 real 数据时显示 honest empty 或 synthetic 模式说明

### 3.4 `/objects`

断言：
- 列表可见
- 支持搜索或筛选
- 点击对象可进入详情页

### 3.5 `/object/:kind/:id`

断言：
- 对象主键可见
- 状态/资格标签可见
- 能跳转至对应画像页或关联证据

### 3.6 `/observation` 与 `/anomalies`

断言：
- 列表或工作区主区域可见
- 统计摘要可见
- 可进入对象或记录详情

### 3.7 `/baseline`

断言：
- baseline version 可见
- 版本上下文与时间信息可见
- 关键摘要区非空

### 3.8 `/initialization`

断言：
- 数据准备步骤列表可见
- 完成与未完成项可区分
- 若关键前置未满足，不得显示全部完成

### 3.9 `/governance`

断言：
- 字段审计模块可见
- ODS 规则模块可见
- trusted 过滤损耗模块可见
- 若为 fallback，必须有显式 banner

### 3.10 `/compare`

断言：
- 对照对象和来源上下文可见
- `data_origin` 与降级/评估说明可见
- 不得误显示为首页主流程页

### 3.11 画像页

断言：
- 主键与标题一致
- 字段标签与冻结口径一致
- 来源说明与对象上下文可见

## 4. 链路级清单

### 4.1 主流程链路

脚本流程：
1. 打开 `/runs`
2. 进入某个 batch
3. 跳转 `/flow/overview`
4. 再跳转 `/flow/snapshot`
5. 进入 `/objects`
6. 打开某个对象详情
7. 再进入 `/baseline`

断言：
- 过程中上下文不丢失
- `run_id / batch_id / data_origin` 在相关页面可核对

### 4.2 支撑治理链路

脚本流程：
1. 打开 `/initialization`
2. 进入 `/governance`
3. 如满足前置，再进入 `/compare`

断言：
- 初始化页与治理页在语义上连通
- compare 的来源状态与前置条件说明一致

## 5. 与 API / SQL 对照要求

每个 Playwright 场景至少要配一条：

1. 对应 API 抽样返回校验
2. 对应 SQL 摘要校验
3. 页面显示值与 API/SQL 不一致时，记录为 P0 或 P1 差异
