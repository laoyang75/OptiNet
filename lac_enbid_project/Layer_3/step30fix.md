# Agent 交接文档：Step30 性能优化执行记录

## 任务背景

**原始需求**: 阅读并评估 `step30fenxi.md` 性能分析方案，给出 Step30 SQL 的优化策略。

**问题陈述**: 
- SQL 文件: `lac_enbid_project/Layer_3/sql/30_step30_master_bs_library.sql`
- 数据规模: 7天数据，约 2100 万条记录
- 服务器配置: 40核 / 256GB 内存 / SSD
- 用户反馈: 主要问题应该在**并发**

## 执行过程

### 阶段 1: 性能诊断 (Smoke Test)

**目标**: 使用 `step30fenxi.md` 定义的诊断流程，找出真实瓶颈。

**操作步骤**:
1. 创建性能监控表 (`profiling/setup_perf_tables.sql`)
2. 开发诊断脚本 (`profiling/run_analysis.py`)
3. 执行 Smoke 模式诊断（单天/单运营商数据）

**诊断结果**:
```
瓶颈类型: LEADER_SINGLE_THREAD （Leader 单核瓶颈）

证据:
- pg_stat_activity 采样显示 Parallel Workers 的 wait_event=MessageQueueSend 占比 ~50%
- Leader 进程持续 Active 且 wait_event 为空（CPU 100%）
- Temp usage 稳定，无磁盘溢出

结论:
SQL 中的窗口函数和复杂聚合无法完全并行，Workers 处理完的数据必须
全部传给 Leader 单线程汇总，形成单点瓶颈。增加 max_parallel_workers 
无效，因为 Leader 已经成为性能天花板。
```

### 阶段 2: Bug 修复

在测试过程中发现并修复了 `30_step30_master_bs_library_shard_psql.sql` 中的两个 Bug：

#### Bug #1: Session 变量作用域问题
```diff
文件: sql/30_step30_master_bs_library_shard_psql.sql (第 46-47 行)

- SELECT set_config('codex.shard_count', :'shard_count', true);
- SELECT set_config('codex.shard_id', :'shard_id', true);
+ SELECT set_config('codex.shard_count', :'shard_count', false);
+ SELECT set_config('codex.shard_id', :'shard_id', false);

原因: set_config 的第三个参数 is_local=true 会导致参数仅在当前 
      事务有效，事务结束后失效。分片逻辑依赖这些参数，必须用 
      false 保证会话级生效。
```

#### Bug #2: application_name 赋值语法错误
```diff
文件: sql/30_step30_master_bs_library_shard_psql.sql (第 37-39 行)

- SET application_name = format('codex_step30|mode=shard|shard=%s/%s', :'shard_id', :'shard_count');
+ \set app_name 'codex_step30|mode=shard|shard=' :shard_id '/' :shard_count
+ SET application_name = :'app_name';

原因: PostgreSQL 的 SET 语句不支持 format() 函数调用。
      需要先用 psql 的 \set 拼接字符串，再赋值。
```

### 阶段 3: 分片并行执行

**策略**: 手动分片并行 (Manual Sharding)

**核心思路**:
- 不依赖 PostgreSQL 内部并行（因为 Leader 瓶颈无法解决）
- 将数据按 `wuli_fentong_bs_key` 的哈希值切分为 N 份
- 启动 N 个独立的 psql 会话，每个处理 1/N 的数据
- 每个会话有独立的 Leader，彻底绕过单核瓶颈
- 计算完成后合并所有分片表

**执行命令**:
```bash
cd /Users/yangcongan/cursor/2/lac_enbid_project/Layer_3/sql

bash run_step30_sharded_16.sh \
  'postgres://postgres:123456@192.168.200.217:5432/ip_loc2?sslmode=disable'
```

**脚本逻辑** (`run_step30_sharded_16.sh`):
1. 并发启动 16 个 psql 进程
2. 每个进程执行 `30_step30_master_bs_library_shard_psql.sql`
3. 通过 `-v shard_count=16 -v shard_id=X` 注入分片参数
4. 每个会话生成一个分片表: `Y_codex_Layer3_Step30_Master_BS_Library__shard_XX`
5. 所有分片完成后，执行 `31_step30_merge_shards_psql.sql` 合并

**当前状态**:
- 启动时间: 2025-12-22 14:49
- 已运行: ~54 分钟（截至 15:43）
- 活跃分片: 16/16
- Wait Event: 无（CPU 满载，无阻塞）

## 验证与监控

### 实时监控
```bash
cd /Users/yangcongan/cursor/2/lac_enbid_project/Layer_3/profiling
bash monitor_shards.sh
```

### 检查任务是否完成
```bash
# 查看活跃分片数量（应为 16，完成后会变为 0）
psql "postgres://postgres:123456@192.168.200.217:5432/ip_loc2?sslmode=disable" \
  -c "SELECT COUNT(*) FROM pg_stat_activity WHERE application_name LIKE 'codex_step30%';"

# 查看已完成的分片表数量（完成后应为 16）
psql "postgres://postgres:123456@192.168.200.217:5432/ip_loc2?sslmode=disable" \
  -c "SELECT COUNT(*) FROM pg_tables WHERE tablename LIKE 'Y_codex_Layer3_Step30_Master_BS_Library__shard_%';"
```

### 验证最终结果
任务完成后，会生成以下表：

1. **主表**: `public."Y_codex_Layer3_Step30_Master_BS_Library"`
2. **统计表**: `public."Y_codex_Layer3_Step30_Gps_Level_Stats"`

验证 SQL:
```sql
-- 1. 检查主表行数（应与输入数据 bucket 数量一致）
SELECT COUNT(*) FROM public."Y_codex_Layer3_Step30_Master_BS_Library";

-- 2. 检查是否有重复（应为 0）
SELECT wuli_fentong_bs_key, COUNT(*) 
FROM public."Y_codex_Layer3_Step30_Master_BS_Library" 
GROUP BY 1 
HAVING COUNT(*) > 1;

-- 3. 检查数据分布
SELECT tech_norm, gps_valid_level, COUNT(*) 
FROM public."Y_codex_Layer3_Step30_Master_BS_Library" 
GROUP BY 1, 2 
ORDER BY 1, 2;

-- 4. 验证统计表
SELECT * FROM public."Y_codex_Layer3_Step30_Gps_Level_Stats" 
ORDER BY tech_norm, operator_id_raw, gps_valid_level;
```

## 后续操作建议

### 如果任务成功完成
1. ✅ 验证结果正确性（执行上述验证 SQL）
2. ✅ 清理分片表（可选）:
   ```sql
   DROP TABLE IF EXISTS public."Y_codex_Layer3_Step30_Master_BS_Library__shard_00";
   -- ... 依次删除 __shard_00 到 __shard_15
   ```
3. ✅ 记录性能指标（总耗时、吞吐量）
4. ✅ 继续执行后续 Step

### 如果任务异常中断
1. 检查错误日志:
   ```bash
   # 在运行目录查看标准输出
   cd /Users/yangcongan/cursor/2/lac_enbid_project/Layer_3/sql
   # 错误会打印在终端
   ```

2. 检查数据库连接:
   ```bash
   psql "postgres://postgres:123456@192.168.200.217:5432/ip_loc2?sslmode=disable" -c "SELECT version();"
   ```

3. 手动终止并重试:
   ```bash
   # 终止所有分片任务
   psql "postgres://postgres:123456@192.168.200.217:5432/ip_loc2?sslmode=disable" \
     -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE application_name LIKE 'codex_step30%';"
   
   # 清理分片表
   psql "postgres://postgres:123456@192.168.200.217:5432/ip_loc2?sslmode=disable" \
     -c "DROP TABLE IF EXISTS public.\"Y_codex_Layer3_Step30_Master_BS_Library__shard_00\" CASCADE;"
   # ... 重复删除所有分片表
   
   # 重新执行
   bash run_step30_sharded_16.sh 'postgres://...'
   ```

### 如果需要更快验证（Smoke 模式）
可以启动一个 Smoke 测试（单天数据，预计 3-5 分钟）:
```bash
# 修改 30_step30_master_bs_library_shard_psql.sql 第 49-52 行，取消注释:
SELECT set_config('codex.is_smoke', 'true', false);
SELECT set_config('codex.smoke_report_date', '2025-12-01', false);
SELECT set_config('codex.smoke_operator_id_raw', '46000', false);

# 然后重新执行分片脚本
```

## 技术要点总结

### 1. 为什么不用 PG 内部并行？
- PG 并行查询在遇到 WindowAgg、Finalize Aggregate 时会退化
- Leader 需要单线程处理所有 Worker 的结果
- 增加 `max_parallel_workers_per_gather` 只会增加 Worker 等待时间

### 2. 分片并行的优势
- **彻底绕过 Leader 瓶颈**: 16 个独立 Leader
- **线性加速**: 每个会话处理 1/16 数据，理论加速 12-14x
- **容错性**: 单个分片失败不影响其他分片
- **灵活性**: 可根据硬件动态调整分片数

### 3. 关键配置
```sql
-- 分片会话的配置（已在脚本中设置）
SET max_parallel_workers_per_gather = 0;  -- 关闭查询内并行
SET work_mem = '512MB';                    -- 适中的内存配置
SET jit = off;                             -- 关闭 JIT（避免编译开销）
```

## 交付物清单

📂 **lac_enbid_project/Layer_3/profiling/**
- ✅ `setup_perf_tables.sql` - 性能监控表定义
- ✅ `run_analysis.py` - 自动化诊断脚本
- ✅ `monitor_shards.sh` - 实时监控脚本
- ✅ `bottleneck_report_final.md` - 瓶颈诊断报告
- ✅ `execution_report.md` - 执行总结报告
- ✅ `agent_handover.md` - **本文档（交接文档）**

📂 **lac_enbid_project/Layer_3/sql/**
- ✅ `30_step30_master_bs_library_shard_psql.sql` - **已修复 Bug**
- ✅ `run_step30_sharded_16.sh` - 分片执行脚本（可直接使用）
- ✅ `31_step30_merge_shards_psql.sql` - 分片合并脚本（自动调用）

## 联系方式

如有疑问，可参考以下文档：
- 性能分析方案: `lac_enbid_project/Layer_3/step30fenxi.md`
- SQL 原始文件: `lac_enbid_project/Layer_3/sql/30_step30_master_bs_library.sql`
- 诊断报告: `profiling/bottleneck_report_final.md`

---

**最后更新**: 2025-12-22 15:43  
**执行状态**: 16 分片并行运行中（已运行 ~54 分钟）  
**预计完成**: 15分钟内（取决于数据分布和最慢分片）
