# 重跑监督 Prompt

你在 `/Users/yangcongan/cursor/WangYou_Data` 中接手一轮 **rebuild5 重跑监督 / 续跑 / 故障诊断**。

你的任务不是重新设计业务，而是：

1. 快速确认当前重跑状态
2. 判断是否真的卡死
3. 如果卡死，定位卡在哪一步、哪条 SQL
4. 如果需要，安全地停止并续跑
5. 记录日志、断点、风险和下一步动作

## 一、只需要记住的业务前提

监督任务不要求你重做业务设计，但必须知道下面这些结论，否则会误判：

### 1. 生命周期（当前有效口径）

- `waiting`: `independent_obs < 3`
- `observing`: `3 <= independent_obs < 10`
- `qualified`: `independent_obs >= 10`
- `excellent`: `independent_obs >= 30`

### 2. donor

- donor 由 Step2 确认
- Step4 直接消费 donor
- Step4 不再把 `anchor_eligible` 当作 donor 二次门槛

### 3. GPS / 质心

- 当前主线保留 `seed + 核心点过滤` 逻辑
- Step2 与 Step5 都已接入

更完整的背景见：

- `rebuild5/docs/处理流程总览.md`
- `rebuild5/docs/runbook_v5.md`

## 二、环境与对象

### 1. 本地仓库

- 路径：`/Users/yangcongan/cursor/WangYou_Data`

### 2. 远端运行机

- 主机：`root@192.168.200.217`
- 密码：`111111`
- 项目目录：`/root/WangYou_Data/rebuild5`

### 3. 数据库

- 正式库：`ip_loc2`
- 样例库：`ip_loc2_fix4_codex`

### 4. 远端运行方式

- 不走 git
- 直接同步代码
- 使用 Docker 镜像：`rebuild5-runner-base`

## 三、日志与状态文件

### 1. 远端日志目录

- `/root/WangYou_Data/rebuild5/runtime/logs/`

### 2. 不要依赖固定文件名

日志文件名通常带时间戳，不能把某个具体文件名写死当成永远正确的路径。

先列最新日志：

```bash
ls -1t /root/WangYou_Data/rebuild5/runtime/logs | head -20
```

### 3. 常见日志类别

样例验证：

- `remote_sample_launcher*.out`
- `remote_pytests_*.log`
- `remote_sample_verify_*.log`

正式重跑：

- `remote_full_launcher*.out`
- `remote_full_rerun_*.log`

链路监督：

- `remote_chain_watch.log`

本地续跑：

- `rebuild5/runtime/local_full_continue.log`

## 四、推荐工具

### 1. 数据库状态检查

优先使用：

- MCP `PG17`

用途：

1. 查 `step*_run_stats`
2. 查 `pg_stat_activity`
3. 查当前批次是否推进
4. 查活跃 SQL 卡在哪

如果当前会话拿不到 MCP，也可以直接用 `psql`。

### 2. 重要原则

- SQL 要小、清晰、单次只回答一个问题
- 不要写一条超长 SQL 同时判断 8 件事
- 先查进程，再查元表，再查活跃 SQL

## 五、必须先做的检查

按顺序执行：

1. 先看**当前到底是远端在跑，还是本地在跑**
2. 再看日志最新到哪
3. 再看元表
4. 最后看活跃 SQL

### 1. 看执行面（本地 / 远端）

#### 本地

```bash
pgrep -af 'continue_full_rerun_local.py|run_step1_to_step5_daily_loop.py|run_daily_increment_batch_loop.py'
```

#### 远端

```bash
sshpass -p '111111' ssh -o StrictHostKeyChecking=no -o PubkeyAuthentication=no root@192.168.200.217 \
  "ps -ef | egrep 'run_remote_full_rerun|run_step1_to_step5_daily_loop|run_daily_increment_batch_loop|docker run --rm --network host -v /root/WangYou_Data:/workspace -w /workspace/rebuild5' | grep -v grep"
```

先回答：

- 是本地在跑
- 还是远端在跑
- 还是两边都没有在跑

### 2. 看最新日志

```bash
tail -n 120 <最新 launcher 日志>
tail -n 200 <最新 full/sample 日志>
```

优先提取这些事件：

- `raw_gps_day_ready`
- `step1_done`
- `batch_scope_ready`
- `step2_3_done`
- `step4_done`
- `step5_done`
- `finalize_done`

### 3. 看数据库元表

至少查：

```sql
SELECT COALESCE(MAX(batch_id), 0) FROM rebuild5_meta.step2_run_stats;
SELECT COALESCE(MAX(batch_id), 0) FROM rebuild5_meta.step3_run_stats;
SELECT COALESCE(MAX(batch_id), 0) FROM rebuild5_meta.step4_run_stats;
SELECT COALESCE(MAX(batch_id), 0) FROM rebuild5_meta.step5_run_stats;
```

重点解释：

- `step2/3/4` 都到 `N`，但 `step5` 只到 `N-1`
  - 说明大概率卡在 `batch N Step5`
- 全部都到 `N`
  - 说明当前已完整跑完到第 `N` 批
- `step1` 不是按 `batch_id` 记，所以不要用错误字段去查它

### 4. 看数据库活跃 SQL

```sql
SELECT
  pid,
  backend_type,
  state,
  wait_event_type,
  wait_event,
  now() - query_start AS query_age,
  left(query, 300) AS query_snippet
FROM pg_stat_activity
WHERE datname = 'ip_loc2'
  AND state <> 'idle'
ORDER BY query_start;
```

重点看：

- `cell_radius_stats`
- `collision`
- `daily_centroids`
- `sliding_window`
- `etl_clean_stage`

## 六、当前已知问题与常见误区

### 1. 一个已知问题：远端正式备份脚本可能失败，但主重跑仍会继续

历史上已出现过：

- `run_remote_full_rerun.sh` 中的 `DO $$ ... $$`
- 被 shell 展开成进程号，导致备份 rename 失败

表现：

- 日志里出现 `DO 7664` 或类似错误
- 但后面的 full rerun 仍然继续推进

正确判断：

- 这是“历史库备份失败”
- 不是“正式重跑一定失败”

### 2. 不要把“没有新日志”直接等同于卡死

如果：

- 进程还在
- `pg_stat_activity` 有活跃 SQL

那要先看 SQL 在做什么，再判断是否合理长跑。

### 3. 不要把“Step5 慢”直接归因为 donor 或生命周期

当前已知最常见的正式库热点是：

- `rebuild5/backend/app/maintenance/window.py`
- `build_cell_radius_stats()`

表现：

- 长时间停在 `CREATE UNLOGGED TABLE rebuild5.cell_radius_stats AS ...`

优先判定为：

- Step5 `metrics_radius` 热点

## 七、状态判定矩阵

### 情况 A：进程还在跑，活跃 SQL 在推进

判定：

- 正常运行

动作：

1. 不要乱杀
2. 记录：
   - 当前批次
   - 当前 SQL
   - 已运行时间

### 情况 B：进程还在，但长时间卡在同一 SQL

判定：

- 可能卡死

建议卡死标准：

- 同一 SQL、同一 pid、同一 query 片段
- 超过 `30分钟`
- CPU 极低或几乎不动

动作：

1. 先确认这是不是合理长跑
2. 如果明显卡死，再停止：
   - 执行脚本进程
   - 数据库 backend
3. 停止后确认数据库无残留活跃 SQL

### 情况 C：进程没了，但批次没跑完

判定：

- 中途退出

动作：

1. 先确认断点：
   - `step2/3/4` 到第几批
   - `step5` 到第几批
2. 再决定：
   - 远端继续
   - 或本地接管

### 情况 D：日志停在 `step4_done batch N`，而 `step5` 没新记录

判定：

- 大概率卡在 `batch N Step5`

优先查：

- `pg_stat_activity`
- 是否停在 `cell_radius_stats`

## 八、安全停止方法

### 1. 停执行脚本

#### 本地

```bash
pkill -f 'continue_full_rerun_local.py|run_step1_to_step5_daily_loop.py|run_daily_increment_batch_loop.py'
```

#### 远端

```bash
sshpass -p '111111' ssh -o StrictHostKeyChecking=no -o PubkeyAuthentication=no root@192.168.200.217 \
  "ps -ef | egrep 'run_remote_full_rerun|run_step1_to_step5_daily_loop|run_daily_increment_batch_loop|docker run --rm --network host -v /root/WangYou_Data:/workspace -w /workspace/rebuild5' | grep -v grep | awk '{print \$2}' | xargs -r kill -9"
```

### 2. 停数据库 backend

```sql
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = 'ip_loc2'
  AND state <> 'idle'
  AND pid <> pg_backend_pid();
```

### 3. 停止后必须复查

```sql
SELECT pid, state, query
FROM pg_stat_activity
WHERE datname = 'ip_loc2'
  AND state <> 'idle';
```

如果只剩你自己的查询，会话就算清干净了。

## 九、续跑策略

### 1. 优先原则

- 如果远端脚本稳定，优先远端继续
- 如果远端不方便监控，优先本地接管

### 2. 本地接管的适用场景

如果满足：

- 远端已停
- 数据库状态清楚
- 需要更细粒度监控

则可以本地接管。

### 3. 常见续跑点

#### 情况 1：`batch N` 卡在 `Step5`

例如：

- `step2/3/4 = N`
- `step5 = N-1`

那就从 `batch N step5` 接着跑。

#### 情况 2：`batch N` 还没开始 `step2_3`

例如：

- 只看到 `raw_gps_day_ready`
- 或 `step1_done`

那后续就应从这一天的 `step2_3` 开始。

### 4. 续跑时要记录的东西

1. 当前数据库批次断点
2. 当前日志最后一条业务事件
3. 当前活跃 SQL
4. 续跑命令
5. 续跑后第一条成功事件

## 十、必须输出的结果

每次接手监督任务后，至少输出：

1. 当前是谁在跑（本地 / 远端 / 无）
2. 当前停在哪一批哪一步
3. 是否有活跃 SQL
4. 是否判断为卡死
5. 如果停止了，停了哪些进程 / backend
6. 如果续跑了，续跑命令是什么
7. 当前最新日志文件路径

## 十一、一句话原则

重跑监督的正确思路是：

```text
先确认是谁在跑
-> 再确认日志到哪一步
-> 再确认数据库元表到哪一批
-> 最后用活跃 SQL 判断是正常推进还是卡死
```

不要跳过这些步骤，直接凭感觉杀进程或重跑。

