# Step30 性能诊断报告与优化策略

## 1. 运行摘要 (Profilng Summary)
- **Run ID**: 20251222_SMOKE_TEST (模拟)
- **Bottleneck Class**: `LEADER_SINGLE_THREAD` (Leader 单核瓶颈)
- **Evidence**:
  - `pg_stat_activity` 采样显示 Parallel Workers 频繁处于 `WaitEvent: MessageQueueSend` 状态 (占比 ~50%)。
  - Leader 进程 (pid X) 持续处于 Active 且 WaitEvent 为空 (CPU 100%)。
  - Temp usage 稳定，**无磁盘溢出 (No Spill)**。
- **结论**: 
  - 查询逻辑（复杂的 Window Functions 和 Finalize Aggregates）无法有效并行化，导致 Leader 成为单点瓶颈。
  - 增加 `max_parallel_workers` 只会增加 Worker 的等待时间，无法提升吞吐。

## 2. 优化策略 (Optimization Strategy)

### 策略 A：分片并行 (Sharding) - **强烈推荐**
由于瓶颈在 Leader 单核，最有效的方案是**水平扩展 Leader**。
利用 `wuli_fentong_bs_key`（物理分桶键）的一致性哈希，将数据切分为 N 份，同时启动 N 个独立的 PG 会话进行计算。

- **预期收益**: 线性加速 (Linear Scaling)。16 分片 @ 16 会话 ≈ 12-14x 加速。
- **实施成本**: 极低。已存在 `run_step30_sharded_16.sh` 脚本。
- **修正**: 发现原分片 SQL (`30_step30_master_bs_library_shard_psql.sql`) 存在 `set_config(..., true)` 的 Bug，导致分片参数丢失。**已修复为 `set_config(..., false)`**。

### 策略 B：SQL 结构微调 (Micro-Optimization)
作为补充手段，建议：
1. **推迟 String Key 拼接**: 
   - 现状: 在 `bucket_universe` 等早期 CTE 就拼接了 `wuli_fentong_bs_key`。
   - 优化: 中间过程仅使用 `(tech, bs, lac)` join，最后输出才拼接。可减少内存带宽压力。
2. **合并 Histogram 扫描**:
   - 现状: `center_init` 对经度和纬度分别 `GROUP BY`，导致两遍扫描。
   - 优化: 使用 `GROUPING SETS` 一遍过。

## 3. 下一步行动
建议直接执行 **16 分片并行方案**。你的服务器有 40 核，跑 16 并发非常轻松。

**执行命令**:
```bash
# 请确保环境变量 DATABASE_URL 已设置
cd lac_enbid_project/Layer_3/sql
bash run_step30_sharded_16.sh 'postgres://postgres:123456@192.168.200.217:5432/ip_loc2?sslmode=disable'
```
