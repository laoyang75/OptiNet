# upgrade v2 收尾 + 调优报告(终)

## 0. TL;DR

- v1 dumpall + post-distribute path failed; v2 fresh rebuild path completed, then this finalize pass completed endpoint scope fix, PG18 tuning, full rerun, and port cutover.
- New production: `192.168.200.217:5488/yangca`, PostgreSQL 18.3, Citus 14.0-1, PostGIS 3.6.3, `/dev/shm=16G`, `dynamic_shared_memory_type=posix`.
- Fallback: old PostgreSQL 17.6 / Citus 14.0-1 is running on `5487`, metadata updated to worker port `5487`, old data directories preserved.
- Full tuned rerun wall clock: `7691.43s` = `128.19 min`, vs loop_optim 03 `8540.62s`, about `9.9%` faster.
- TCL b7: `340,766`, deviation vs loop_optim 03 `340,766` = `0.000000%`; 8 drift_pattern categories present.
- Checkpoint cadence improved from prior `17-30s` warnings to roughly `10-22min` on coordinator and about `15min` on workers during the rerun.
- Cutover timestamp: `2026-04-27 18:06:36-18:06:45 Asia/Shanghai`, measured 5488 downtime `9s`.
- New `5488` runbook `sentinels.sh 7` and `endpoint_check.sh` PASS after cutover.

## 1. Phase 1 State

Initial 5491 state before tuning:

- PostgreSQL 18.3 `(Debian 18.3-1.pgdg12+1)`
- Extensions: Citus 14.0-1, PostGIS 3.6.3, pg_stat_statements 1.12, plpgsql
- Active workers: 216/219/220/221 on port `5491`
- TCL batches: b1=79,451, b2=158,067, b3=211,324, b4=252,687, b5=286,291, b6=314,489, b7=342,581
- `cell_sliding_window`: 23,748,385 rows, `2025-12-01..2025-12-07`
- `enriched_records`: only batch 7 remained, 3,517,690 rows, because it is intentionally UNLOGGED
- Initial tuning gaps: `max_wal_size=1GB`, `effective_cache_size=4GB`, `dynamic_shared_memory_type=mmap`

## 2. Endpoint Scope Fix

Changed `rebuild5/scripts/runbook/endpoint_check.sh`:

- Replaced `enriched_7_batch_coverage` with `enriched_latest_batch`.
- The latest batch is anchored to LOGGED `rb5.trusted_cell_library`.
- UNLOGGED `rb5.enriched_records` is checked only for that current batch: rows > 0, strict single day, `off_day_rows=0`.

Changed `rebuild5/scripts/runbook/sentinels.sh`:

- Renamed the enriched check to `enriched_current_batch_single_day`.
- Batch 1 Path-A empty remains allowed.
- Batch >1 now requires enriched rows > 0 and strict single-day scope.
- Fixed the FAIL path to return non-zero reliably by forcing an SQL error under `ON_ERROR_STOP=1`; psql `\quit 1` did not work in this environment.

`reset_step1_to_step5_for_full_rerun_v3.sql` also now drops `rb5.step2_batch_input` as a view before attempting table cleanup, matching the artifact runner compatibility view.

## 3. PG18 Tuning

Applied in 5 ordered ALTER SYSTEM groups on all 5 PG18 nodes, each followed by `pg_reload_conf()` and a coordinator TCL count check:

| Group | Parameters | Effective |
| --- | --- | --- |
| WAL/checkpoint | `max_wal_size=64GB`, `min_wal_size=8GB`, `checkpoint_timeout=15min`, `checkpoint_completion_target=0.9`, `wal_compression=lz4`, `wal_buffers=64MB` | reload except `wal_buffers` restart |
| Cost | `effective_cache_size=180GB`, `random_page_cost=1.2` | reload |
| IO | `io_method=worker`, `io_workers=10`, `effective_io_concurrency=64`, `maintenance_io_concurrency=64` | reload |
| Parallel | `max_worker_processes=32`, `max_parallel_workers=24`, `max_parallel_workers_per_gather=4`, `max_parallel_maintenance_workers=4` | `max_worker_processes` restart, rest reload |
| Memory | `work_mem=128MB`, `maintenance_work_mem=8GB`, `shared_buffers=64GB` | `shared_buffers` already 64GB, restart confirmed |

After container restart, all 5 nodes showed:

- `shared_buffers=64GB`
- `dynamic_shared_memory_type=posix`
- `max_worker_processes=32`
- `max_wal_size=64GB`
- `wal_buffers=64MB`

## 4. Container Rebuild

Before rebuilding, current 5491 container inspect JSON was saved under:

- `/nas_vol8/upgrade/configs/v2_container_inspect_<host>_<timestamp>.json`

The new PG18 5491 containers preserved:

- Image: `optinet/citus:14.0.0-pg18.3-postgis3.6.3`
- Env: `POSTGRES_PASSWORD=123456`, `POSTGRES_USER=postgres`
- Volumes:
  - coordinator: `/data/pgsql/18-fresh/coordinator/pgroot:/var/lib/postgresql`
  - workers: `/data/pgsql/18-fresh/worker/pgroot:/var/lib/postgresql`

Added runtime hardening:

- `--shm-size=16g`
- `--restart unless-stopped`
- `--stop-timeout=300`
- `--ulimit nofile=1048576:1048576`

Verified `/dev/shm` as `16G` on all 5 PG18 containers.

## 5. Tuned Full Rerun

The full rerun used:

```bash
REBUILD5_PG_DSN='postgres://postgres:123456@192.168.200.217:5491/yangca' \
python3 rebuild5/scripts/run_citus_artifact_pipelined.py \
  --start-day 2025-12-01 --end-day 2025-12-07 --start-batch-id 1
```

Runner summary:

| Batch | Day | Artifact rows | TCL rows | Runner duration(s) |
| ---:| --- | ---:| ---:| ---:|
| 1 | 2025-12-01 | 4,682,393 | 79,452 | 1,092.92 |
| 2 | 2025-12-02 | 4,740,558 | 158,068 | 1,349.92 |
| 3 | 2025-12-03 | 4,386,568 | 211,324 | 1,659.25 |
| 4 | 2025-12-04 | 4,263,579 | 252,687 | 2,091.14 |
| 5 | 2025-12-05 | 4,167,579 | 286,290 | 2,759.52 |
| 6 | 2025-12-06 | 4,157,405 | 314,489 | 3,461.25 |
| 7 | 2025-12-07 | 4,428,601 | 340,766 | 4,475.43 |

Total wall clock: `7691.43s`, about `128.19 min`.

Compared with loop_optim 03 `8540.62s`, this run is faster by about `849.19s`, or `9.9%`.

## 6. Acceptance

New 5491 before cutover:

- `sentinels.sh 7`: PASS
- `endpoint_check.sh`: PASS
- TCL b7: `340,766`
- TCL b7 deviation vs loop_optim 03: `0.000000%`
- `cell_sliding_window`: 24,017,207 rows, `2025-12-01..2025-12-07`
- `enriched_records`: batches 2-7 present; batch 1 Path-A empty as expected

Drift pattern distribution for batch 7:

| drift_pattern | rows |
| --- | ---:|
| stable | 336,806 |
| insufficient | 2,671 |
| large_coverage | 711 |
| dual_cluster | 465 |
| uncertain | 102 |
| oversize_single | 6 |
| migration | 4 |
| collision | 1 |

Checkpoint cadence:

- Coordinator sampled checkpoints: 07:56, 08:13, 08:30, 08:46, 09:01, 09:14, 09:24, 09:46 UTC; intervals roughly `10-22min`.
- Workers sampled checkpoints were roughly every `15min`.
- No sampled logs showed the prior "checkpoints are occurring too frequently" pattern.

## 7. Port Cutover

Cutover log:

- Start old 5488 stop: `2026-04-27 18:06:36 Asia/Shanghai`
- New 5488 ready: `2026-04-27 18:06:45 Asia/Shanghai`
- Measured 5488 downtime: `9s`

Actions:

- Stopped and removed temporary new `citus-*-5491-fresh` containers.
- Stopped old PG17 `citus-*-5488` containers and renamed them to `*-pg17-archived-20260427_180341`.
- Started new PG18 containers as `citus-coordinator-5488` / `citus-worker-5488`.
- Updated new PG18 Citus metadata from worker port `5491` to `5488`.
- Ran `start_metadata_sync_to_all_nodes()`; all new PG18 nodes have `metadatasynced=true`.
- Started old PG17 fallback as `citus-*-5487-pg17-fallback`.
- Updated old PG17 fallback metadata from `5488` to `5487`; all fallback nodes have `metadatasynced=true`.

Post-cutover verification:

- New `5488`: PostgreSQL 18.3, active workers on 5488, TCL b7=340,766, `sentinels.sh 7` PASS, `endpoint_check.sh` PASS.
- Old `5487`: PostgreSQL 17.6, active workers on 5487, TCL b7=340,766.

Note: the new PG18 containers currently also expose host port `5491` as a temporary compatibility alias. Citus metadata and runbook validation use `5488`.

## 8. Known Limits / Follow-up

- Keep old PG17 `5487` fallback for 1-2 weeks, then remove only after explicit cleanup approval.
- Keep v1 dump `/nas_vol8/upgrade/backups/dumps/yangca_full_20260426_105359.sql` as safety net until the observation window closes.
- The stopped archived PG17 container objects are retained alongside the running 5487 fallback containers; PG17 data directories are unchanged.
- Future data-warehouse work should use new `5488` PG18.
