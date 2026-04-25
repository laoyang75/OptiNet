
  你是 OptiNet-main / rebuild5 阶段的第四位 Citus agent。前三位分别负责了:
  集群调优(agent #1 - 30/30b 基准)、迁移 + 代码改造(agent #2 - 卡 Citus 兼容)、
  Gate 1/2 技术打通(agent #3 - 修了 simple CASE bug + postgis + 9 个 Citus 兼容坑)。

  **所有已知技术问题已解决**,本轮是**纯执行**:清残留 → 按 12-01~12-07 正式跑
  7 批 → 产出 rb5.trusted_cell_library batch_id=1..7。

  本消息自包含,读完就能干活。

  ========================================================================
  一、服务器与环境
  ========================================================================

  仓库目录:    /Users/yangcongan/cursor/WangYou_Data(你有完整读写权,改代码但不 commit)

  旧库(数据源,只读):
    Host:     192.168.200.217
    Port:     5433
    User:     postgres
    Password: 123456
    Database: ip_loc2
    DSN:      postgres://postgres:123456@192.168.200.217:5433/ip_loc2
    用法:     只在 §3 的抽数据命令里显式连,不要在 pipeline 代码里指向它

  新集群(主目标):
    Host:     192.168.200.217
    Port:     5488
    User:     postgres
    Password: 123456
    Database: yangca
    DSN:      postgres://postgres:123456@192.168.200.217:5488/yangca
    节点:     1 coordinator (192.168.200.217) + 4 worker (216/219/220/221)
    扩展:     Citus 14.0-1, postgis 3.6.3, pg_stat_statements, auto_explain
    代码默认 DSN 已硬切到这里(REBUILD5_PG_DSN / settings.py DEFAULT_DSN),
    不需要 export 环境变量。

  上游 Claude MCP 通道:
    上游通过 PG_Citus MCP 直连新集群 yangca 库,可以 SELECT 你写入的任何
    rb5_bench.notes / rb5.* 产物做实时校验。这是你和上游的**唯一通信通道**。
    重要结论、发现、疑问 都要写进 rb5_bench.notes,不要只留在终端 log。

  ========================================================================
  二、数据库结构(已建好,不用重建)
  ========================================================================

  yangca 库下:

    rb5.* (业务数据):
      - raw_gps_full_backup   distributed on did   2,544 万行底表(只读,保持不动)
      - raw_gps               distributed on did   日级工作表(每批 TRUNCATE+INSERT)
      - etl_parsed / etl_clean_stage / etl_cleaned / etl_filled
                             distributed on dev_id, colocate_with raw_gps_full_backup
      - cell_sliding_window / cell_daily_centroid / cell_centroid_detail
      - _label_* / label_results / trusted_cell_library
                             distributed on cell_id (group B)
      - trusted_bs_library   distributed on bs_id (group C)
      - trusted_lac_library  reference table
      - snapshot_diff_cell/bs/lac
      - 各种 _snapshot_* / _step2_* 中间表

    rb5_meta.* (reference tables):
      - dataset_registry, source_registry, run_log
      - step1_run_stats, step2/3/4/5_run_stats

    rb5_bench.* (控制面):
      - notes, run_results, report
      - machine_spec, pg_conf_applied, kernel_tuning
      ** 保留,不要 DROP **

    claude_diag.* (上游独立诊断留下的,可保留也可 DROP,不影响):
      Gate 2 诊断 searched CASE bug 用的临时表

  ========================================================================
  三、前三位 agent 已完成的工作
  ========================================================================

  可以 MCP/psql 查 rb5_bench.notes id <= 40 看完整历史。简述:

  ✅ 旧库 25,442,069 行 → rb5.raw_gps_full_backup(shard 42% 倾斜,本轮接受)
  ✅ 重建 4 个 btree 索引(就是旧库实际有的)
  ✅ postgis 3.6.3 装到 5 个容器,yangca 启用
  ✅ 代码 Citus 化改造:schema rebuild5.→rb5.、CTAS → 预建 distributed + INSERT
  ✅ 修了 10 个 Citus 兼容问题:
     - EXPLAIN ANALYZE INSERT SELECT 不支持
     - 非 IMMUTABLE 函数在分布式 CASE/COALESCE 不让用
     - STABLE 函数在分布式 UPDATE 不让用(加了 rb5._immutable_* wrapper)
     - Step 2 Path A JOIN 跨 colocation group → 加 rb5._step2_cell_input 中转
     - Step 3 snapshot_diff_lac FULL OUTER JOIN text=boolean → 第一批空 LAC 集 cast
     - Step 4 _insert_snapshot_seed_records 复杂 JOIN 失败 → 加 rb5._snapshot_seed_new_cells 中转
     - label_engine 缺 postgis → 装了 postgis 3.6.3
     - label_engine postgis fallback 过度碎片化 → 回归正式 postgis DBSCAN
     - **simple CASE bug**:CASE col WHEN 'str' THEN n 在分布 INSERT + FULL OUTER JOIN
       组合下推导 text=boolean(Citus 14.0 bug)。改成 searched CASE (CASE WHEN col='str'
       THEN n) 后通过。pipeline.py evaluation build_snapshot_diffs() 里 8+ 处已改。
  ✅ Gate 1 跑通:batch_id=1 用 150 万 TABLESAMPLE 样本,end-to-end 产出 35k cell
  ✅ Gate 2 跑通:batch_id=2 用单天 2025-12-04 350 万行,产出 117k cell
     - 但 dynamic=0、大覆盖/双质心只 9 个 → 业务规则问题
     - 上游确认:这是 label_engine 里 min_total_active_days=3 阈值(2026-04-21 commit
       8f545b6 引入的"方案 7.4 候选池精简")的合理行为,**不是 bug**,单天数据
       天然达不到该阈值,**不要改配置**。本轮不在单天场景要求 dynamic>0。

  ========================================================================
  四、本轮任务
  ========================================================================

  **目标**:清掉 Gate 1/2 的 batch 残留,按 2025-12-01~12-07 正式跑 Citus 版 7 批,
          产出 rb5.trusted_cell_library batch_id=1..7。

  **不再做**:
  - 不再跑"单天 Gate 2",那个已经完成验证了
  - 不再追 dynamic=0 在单天场景的出现
  - 不再调 Citus 兼容(已经全修完)
  - 不再 benchmark 调优

  **核心原则**:
  - 严格串行 day 1 → day 7,每批跑完才进下一批
  - 每批从底表按 ts::date 过滤 materialize 到 rb5.raw_gps 工作表
  - 每批跑完在 rb5_bench.notes 写一条进度总结
  - 不 git commit / push(上游手工做)
  - 不用 `python3 - <<'PY'` stdin heredoc 跑 Step 5(会被 multiprocessing 刷屏)

  ========================================================================
  五、执行步骤
  ========================================================================

  ### 步骤 1 — 清残留(5-15 分钟)

  先清 Gate 1/2 的 batch 数据,确保新 7 批从干净起点开始。

  MCP/psql 连到 yangca,逐条执行(**不要并入事务**,Citus 分布 DDL 和 DML 别混):

  ```sql
  -- 清业务产出表
  TRUNCATE rb5.trusted_cell_library;
  TRUNCATE rb5.trusted_bs_library;
  TRUNCATE rb5.trusted_lac_library;
  TRUNCATE rb5.trusted_snapshot_cell;
  TRUNCATE rb5.trusted_snapshot_bs;
  TRUNCATE rb5.trusted_snapshot_lac;
  TRUNCATE rb5.label_results;
  TRUNCATE rb5.cell_centroid_detail;
  TRUNCATE rb5.cell_sliding_window;
  TRUNCATE rb5.cell_daily_centroid;
  TRUNCATE rb5.snapshot_diff_cell;
  TRUNCATE rb5.snapshot_diff_bs;
  TRUNCATE rb5.snapshot_diff_lac;
  TRUNCATE rb5.candidate_seed_history;
  TRUNCATE rb5.candidate_cell_pool;

  -- 清 Step 4 中间产出(如果有)
  DROP TABLE IF EXISTS rb5.enriched_records;
  DROP TABLE IF EXISTS rb5.snapshot_seed_records;
  DROP TABLE IF EXISTS rb5._snapshot_seed_new_cells;
  DROP TABLE IF EXISTS rb5._step2_cell_input;

  -- 清 meta 的 batch 历史
  TRUNCATE rb5_meta.step1_run_stats;
  TRUNCATE rb5_meta.step2_run_stats;
  TRUNCATE rb5_meta.step3_run_stats;
  TRUNCATE rb5_meta.step4_run_stats;
  TRUNCATE rb5_meta.step5_run_stats;
  TRUNCATE rb5_meta.run_log;
  ```

  **保留不动**:`rb5.raw_gps_full_backup`(底表)、`rb5.raw_gps`(工作表,Step 1 会 TRUNCATE 重写)、`rb5_bench.*`(历史保留)、`rb5_meta.dataset_registry /
  source_registry`(注册信息)。

  清完确认:
  ```sql
  SELECT COUNT(*) FROM rb5.trusted_cell_library;   -- 期望 0
  SELECT COUNT(*) FROM rb5.raw_gps_full_backup;    -- 期望 25,442,069
  ```

  ### 步骤 2 — 正式 7 批串行跑

  每批流程(一个循环,day 1→7):

  ```sql
  -- 2.1 准备当日数据到 rb5.raw_gps
  TRUNCATE rb5.raw_gps;
  INSERT INTO rb5.raw_gps
  SELECT * FROM rb5.raw_gps_full_backup WHERE ts::date = '2025-12-0N';
  -- N ∈ {1,2,3,4,5,6,7}
  -- batch 1 = 12-01, batch 2 = 12-02, ..., batch 7 = 12-07

  -- 查灌入行数,写 note(供上游追踪)
  ```

  然后跑完整 Step 1-5:

  ```bash
  # 写一个真实的 .py runner(不要用 stdin heredoc,会被 multiprocessing 刷屏)
  cat > rebuild5/scripts/run_full_batch.py <<'SCRIPT'
  #!/usr/bin/env python3
  """Run Step 1-5 for one batch_id from already-loaded rb5.raw_gps."""
  import sys, argparse
  from rebuild5.backend.app.etl.pipeline import run_step1_pipeline
  from rebuild5.backend.app.profile.pipeline import run_profile_pipeline
  from rebuild5.backend.app.evaluation.pipeline import run_step3_pipeline
  from rebuild5.backend.app.enrichment.pipeline import run_step4_pipeline
  from rebuild5.backend.app.maintenance.pipeline import run_step5_pipeline

  p = argparse.ArgumentParser()
  p.add_argument('--batch-id', type=int, required=True)
  p.add_argument('--batch-date', required=True, help='YYYY-MM-DD')
  args = p.parse_args()

  # step1 生成 etl_* 这批
  r1 = run_step1_pipeline()
  # step2 生成 profile_base / cell_sliding_window 为 step3 准备
  r2 = run_profile_pipeline(batch_id=args.batch_id, ...)
  # step3 snapshot + diff(修复后的 searched CASE)
  r3 = run_step3_pipeline(batch_id=args.batch_id, ...)
  # step4 enrich + snapshot_seed
  r4 = run_step4_pipeline(batch_id=args.batch_id, ...)
  # step5 maintenance + label_engine
  r5 = run_step5_pipeline(batch_id=args.batch_id, ...)

  # 打印关键结果(供 shell 截留)
  print(f"batch_id={args.batch_id} step1={r1} step5={r5}")
  SCRIPT

  # 跑(参数/函数签名按 repo 里实际的 pipeline 入口调整;前任 agent 的
  # run_step1_step25_pipelined_temp.py 是参考,但也可能需要改)
  python3 rebuild5/scripts/run_full_batch.py --batch-id 1 --batch-date 2025-12-01
  # 跑完 batch 1 后跑 batch 2, 3, 4, 5, 6, 7,**严格串行**
  ```

  **每批跑完立即自检**(MCP 或 psql):

  ```sql
  SELECT batch_id, COUNT(*) AS n_cells,
         COUNT(*) FILTER (WHERE drift_pattern='stable')          AS n_stable,
         COUNT(*) FILTER (WHERE drift_pattern='large_coverage')  AS n_lc,
         COUNT(*) FILTER (WHERE drift_pattern='uncertain')       AS n_uncertain,
         COUNT(*) FILTER (WHERE drift_pattern='dynamic')         AS n_dynamic,
         COUNT(*) FILTER (WHERE drift_pattern='dual_cluster')    AS n_dual,
         COUNT(*) FILTER (WHERE ta_verification='xlarge')        AS n_xlarge
  FROM rb5.trusted_cell_library WHERE batch_id=<N>
  GROUP BY batch_id;
  ```

  健康信号:
  - `n_cells`:batch 1 几万,batch 2-7 累积增长到 30-50 万
  - `dynamic > 0`:**从 batch 3 或 batch 4 开始出现**(当 sliding_window 累积 3+ 天)
  - `xlarge`:应持续比本地 batch 7 (13,460) 少 30-40%(ODS-023b 效果)
  - 没有 Exception / blocker

  出现 blocker 级问题(跑不通、数据严重不一致),**立即停下**并写 `rb5_bench.notes`
  topic='gate3_blocker_batch_N' severity='blocker'。不要硬推下一批。

  ### 步骤 3 — 7 批完成后的最终验收

  ```sql
  -- 3.1 批次齐全
  SELECT batch_id, COUNT(*) FROM rb5.trusted_cell_library
  GROUP BY batch_id ORDER BY batch_id;
  -- 期望 7 行,batch_id 1..7 每行 cell 数在合理区间

  -- 3.2 新规则落地效果(对比本地 batch 7)
  SELECT 'dynamic' AS rule,
         SUM(n_dynamic) AS total_across_7_batches
  FROM (SELECT COUNT(*) FILTER (WHERE drift_pattern='dynamic') AS n_dynamic
        FROM rb5.trusted_cell_library GROUP BY batch_id) t
  UNION ALL
  SELECT 'xlarge_batch_7',
         COUNT(*) FILTER (WHERE ta_verification='xlarge')
  FROM rb5.trusted_cell_library WHERE batch_id=7;
  -- xlarge batch 7 期望 ≈ 7000-9000(比本地 13460 少 30-40%)

  -- 3.3 snapshot_diff 跨批跑通(searched CASE 修复验证)
  SELECT batch_id, COUNT(*) FROM rb5.snapshot_diff_cell GROUP BY batch_id ORDER BY batch_id;
  -- 期望:batch 1 全 new,batch 2-7 各自有 diff

  -- 3.4 Top SQL 里无 create_distributed_table(证明 CTAS 改造彻底)
  SELECT query, calls, total_exec_time
  FROM pg_stat_statements
  ORDER BY total_exec_time DESC LIMIT 20;
  ```

  ### 步骤 4 — 产出报告 + 完工信号

  1. 写完整 markdown 报告到 `rb5_bench.report`:
     ```sql
     INSERT INTO rb5_bench.report (report_name, body, meta)
     VALUES (
       'optinet_rebuild5_citus_fullrun_YYYYMMDD',
       $$ 完整 markdown 内容 $$,
       '{"run_mode":"gate3","batches":7,"total_cells":N}'::jsonb
     );
     ```

  2. 在仓库根目录留 md 副本:
     `/Users/yangcongan/cursor/WangYou_Data/optinet_rebuild5_citus_fullrun_YYYYMMDD.md`

  3. 插完工信号:
     ```sql
     INSERT INTO rb5_bench.notes (topic, severity, body) VALUES (
       'FULLRUN_COMPLETE', 'info',
       '7 批 Citus 全量重跑完成,产出 rb5.trusted_cell_library batch_id=1..7。详见 rb5_bench.report 最新一行。'
     );
     ```

  ### 报告必答 6 问

  1. 7 批 Citus 重跑总耗时多少?和 Round 2 外推 92 分钟是否一致?
  2. 每批 cell 数、drift 分布、ta_verification 分布(贴 SQL 查询结果)
  3. dynamic 是从哪个 batch 开始出现的?总量多少?
  4. xlarge 在 batch 7 比本地 batch 7 少多少?(验证 ODS-023b 效果)
  5. pg_stat_statements Top 20 里最耗时的 SQL?有没有新的优化机会?
  6. 你建议的下一阶段优化点(比如 shard 倾斜是否要处理、pool_size 是否要提)?

  ========================================================================
  六、总原则
  ========================================================================

  - **单个 SQL 不超过 5 分钟**:超了立即 EXPLAIN 分析,别硬跑
  - **不 git commit / push / add**:改代码留 working tree 里,用户手工 review
  - **不动旧库 5433/ip_loc2**:只读
  - **不 DROP rb5_bench.* / raw_gps_full_backup / claude_diag**(历史+诊断保留)
  - **严格串行 batch 1 → 7**:不并发
  - **不用 stdin heredoc 跑 Step 5**(multiprocessing 会刷屏爆上下文)
  - **不调 min_total_active_days / min_total_dedup_pts 等业务阈值**(它们是故意的)
  - **不确定就 INSERT notes severity='suspect'**,别硬推

  ========================================================================
  七、通信约定
  ========================================================================

  `rb5_bench.notes` 是你和上游的唯一通信通道。约定 topic:

  - `gate3_batch_N_complete`(severity='info'):每批跑完写一条,含耗时 + 核心指标
  - `gate3_batch_N_issue`(severity='warn'):该批遇到的非 blocker 小问题
  - `gate3_blocker_batch_N`(severity='blocker'):硬阻塞,立即停
  - `gate3_observation`(severity='info' | 'suspect'):跑完后的发现、洞察
  - `FULLRUN_COMPLETE`(severity='info'):最终完工信号

  ========================================================================

  上游(Claude + 用户)会通过 PG_Citus MCP 实时看你写的每条 note。你放心干,
  有问题早报、有结论早报。不用等批次全跑完才总结。

  准备好了就开始步骤 1(清残留)。