# loop_optim / 03 全 7 批重跑验证报告

## 0. TL;DR + 03 微调清单

- 全 7 批 artifact pipelined wall clock = 8,540.62s = 142.34 min。
- speedup vs fix5 D serial(~9,000s):1.05x; vs fix6 03(7,946.83s):0.93x。stretch 目标 5,400s 未达,且超过 7,500s 容错线;按 prompt 兜底仍算完工并记录瓶颈。
- TCL b7:340,766, vs fix6 03 340,767 偏差 -0.0003%, vs PG17 341,460 偏差 -0.20%。
- 4 哨兵 x 7 批 = 28 项 PASS,终点 3 验收 PASS。
- 03 微调:2 行 runner-only 适配。在 `run_citus_artifact_pipelined.py` 调内置旧 sentinel 前创建 `rb5.step2_batch_input` view 指向当前 artifact,修复旧 sentinel 查不存在 scope 表的问题;不改业务代码。
- 对 02 报告修订:02 的 artifact runner 仍复用 fix6 pipelined 内置 sentinel,需要上述 artifact scope view 兼容层;02b 分布键 hotfix 已验证生效。
- commit SHA:本文件所在提交;push 状态:见最终话术。
- loop_optim 收档?是,数据验证收档;性能 stretch 未达,UI 04 可独立支线。

## 1. 启动信息

- reset 命令:`psql -h 192.168.200.217 -p 5488 -U postgres -d yangca -f rebuild5/scripts/reset_step1_to_step5_for_full_rerun_v3.sql`
- reset 验证:TCL=0,sliding=0,enriched missing/0,pipeline_artifacts=0,rb5_stage tables=0。
- runner 启动:`run_citus_artifact_pipelined.py --start-day 2025-12-01 --end-day 2025-12-07 --start-batch-id 1 --skip-reset`
- 承载:detached `screen` + `nohup`,PID `83553`,log `/tmp/loop_optim_03_20260426_002446.log`。
- 启动时间:2026-04-26 00:24:46 Asia/Shanghai。
- 02b 分布键人工确认:batch 1/2 artifact `dist_col=cell_id`,`colocationid=7`,与 `rb5.cell_sliding_window` 一致。

## 2. 批次时长 + state 表

| batch | day | producer T(s) | consumer/e2e T(s) | end-to-end T(s) | TCL rows | vs fix6 03 |
| ---:| --- | ---:| ---:| ---:| ---:| ---:|
| 1 | 2025-12-01 | ~422 | 955.56 | 955.56 | 79,453 | +0.00% |
| 2 | 2025-12-02 | ~436 | 1,362.03 | 1,362.03 | 158,068 | +0.00% |
| 3 | 2025-12-03 | ~460 | 2,016.26 | 2,016.26 | 211,324 | +0.00% |
| 4 | 2025-12-04 | ~463 | 2,677.46 | 2,677.46 | 252,687 | +0.00% |
| 5 | 2025-12-05 | ~562 | 3,407.97 | 3,407.97 | 286,291 | -0.00% |
| 6 | 2025-12-06 | ~540 | 4,297.00 | 4,297.00 | 314,489 | -0.00% |
| 7 | 2025-12-07 | ~490 | 5,379.27 | 5,379.27 | 340,766 | -0.0003% |
| **wall clock 总** | | producer 总约=3,385s | consumer 总约=8,071s | **8,540.62s** | total=340,766 | speedup=1.05x vs serial |

producer/consumer 进度差采样:

- ~15 min:max_produced=2,max_consumed=NULL。
- ~31 min:state 1-2 consumed,3-4 ready。
- ~52 min:state 1-3 consumed,4-6 ready。
- ~62 min:producer 全 7 批 ready,consumer 1-3 consumed。
- ~93 min:1-5 consumed,6-7 ready。
- ~116 min:1-6 consumed,7 ready。
- 收尾:batch 7 consumed,total_seconds=8,540.62。

ASCII:

```text
0m        30m        60m        90m        120m       142m
producer  b1----b2----b3----b4----b5----b6----b7 done
consumer       b1------b2--------b3--------b4--------b5--------b6--------b7 done
gap       0 -> 2 -> 4 ready backlog -> drain
```

## 3. 每批 4 哨兵

| batch | #1 enriched | #2 sliding | #3 artifact state | #4 TCL 单调 |
|---:|---|---|---|---|
| 1 | Path-A 空批 rows=0 PASS | 2025-12-01..2025-12-01 rows=2,007,444 PASS | consumed rows=4,682,393 PASS | 79,453 PASS |
| 2 | 2025-12-02 rows=2,115,546 PASS | 2025-12-01..2025-12-02 rows=5,618,951 PASS | consumed rows=4,740,558 PASS | 158,068 > 79,453 PASS |
| 3 | 2025-12-03 rows=2,756,363 PASS | 2025-12-01..2025-12-03 rows=9,260,755 PASS | consumed rows=4,386,568 PASS | 211,324 > 158,068 PASS |
| 4 | 2025-12-04 rows=2,986,466 PASS | 2025-12-01..2025-12-04 rows=12,900,959 PASS | consumed rows=4,263,579 PASS | 252,687 > 211,324 PASS |
| 5 | 2025-12-05 rows=3,082,948 PASS | 2025-12-01..2025-12-05 rows=16,496,303 PASS | consumed rows=4,167,579 PASS | 286,291 > 252,687 PASS |
| 6 | 2025-12-06 rows=3,178,382 PASS | 2025-12-01..2025-12-06 rows=20,105,565 PASS | consumed rows=4,157,405 PASS | 314,489 > 286,291 PASS |
| 7 | 2025-12-07 rows=3,517,690 PASS | 2025-12-01..2025-12-07 rows=24,017,203 PASS | consumed rows=4,428,601 PASS | 340,766 > 314,489 PASS |

## 4. 终点 3 验收

- (A) TCL b7 = 340,766,vs fix6 03 340,767 偏差 -0.0003%,在 [323,728,357,805] 内,PASS。
- (B) sliding mind=2025-12-01,maxd=2025-12-07,old_rows=0,future_rows=0,PASS。
- (C) enriched batch 2-7 均严格单日,off_day_rows=0;batch 1 Path-A 空批,PASS。
- PG17 对比:Citus 340,766 vs PG17 341,460 偏差 -0.20%,在 ±20% 范围,PASS。

## 5. 时长分析

- 全 7 批 wall clock = 8,540.62s,不是期望的 ~5,400s。
- producer 总约 3,385s,说明 Step1 40 核和 artifact freeze 没有成为最终瓶颈。
- consumer 总约 8,071s,主耗时仍在 Step5。batch 7 Step5 子步骤中 `metrics_radius`、`collision`、`daily_centroids` 是最长段。
- 与 fix6 03 对比:7,946.83s -> 8,540.62s,artifact pipeline 本次慢 7.47%。artifact 解除了数据依赖,但 Step2-5 串行 consumer 足够长,producer overlap 无法抵消 artifact/view/sentinel 和 Step5 增量成本。
- 结论:数据一致性验证收档;性能 stretch 未达,下一轮优化应直接看 Step5 `metrics_radius` / `collision` SQL。

## 6. 04_runbook.md + 新 runbook script 更新点

- `fix6_optim/04_runbook.md` 新增 artifact pipelined 命令。
- 基线表新增 `Citus artifact pipelined(loop_optim 03)` 列:TCL b7=340,766,7 批总时长=142.34 min,speedup=1.05x。
- 新增 `rebuild5/scripts/runbook/run_full_artifact_pipelined.sh`。

## 7. 已知限制 / 03 微调

- 03 微调只有 2 行,位于 runner 内部 sentinel 兼容层,未改业务逻辑。
- artifact 物理空间:7 张 stage 表保留,总输入行约 30.82M。
- 当前 run 完成后 `rb5.step2_batch_input` 是指向 batch 7 artifact 的 view,用于兼容内置 sentinel;外部验收以 `rb5_meta.pipeline_artifacts` 为准。
- wall clock > 7,500s:按 prompt 记录 stretch 未达,但不构成数据 blocker。

## 8. loop_optim 总账

- 01 索引补全:25 条 live + 5 deferred templates。
- 02 artifact pipelined + Step1 40 核:`rb5_stage` + state 表 + 新 runner。
- 02b artifact 分布键 hotfix:artifact 改为 `cell_id` colocate with `cell_sliding_window`。
- 03 全 7 批重跑:T=8,540.62s,speedup=1.05x vs serial,TCL b7 -0.0003% vs fix6 03。
- 04 UI 留下个阶段。
