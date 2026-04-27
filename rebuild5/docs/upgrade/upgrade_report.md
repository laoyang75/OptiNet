# upgrade — PG / Citus / 扩展 升级报告

## 0. TL;DR

- 结论:本次升级未完成,已按数据完整性兜底回滚到原 PG17 生产集群。
- 升级前/当前生产:PG 17.6, Citus 14.0-1, PostGIS 3.6.3, Docker `citusdata/citus:14.0.0-pg17`。
- 目标验证:PG 18.3, Citus 14.0-1, PostGIS 3.6.3, 自建镜像 `optinet/citus:14.0.0-pg18.3-postgis3.6.3`。
- 路径:路 B fresh rebuild。`pg_dumpall` 恢复成功,但 Citus 分布元数据重建后切 5488 发现部分分布表数据不可见。
- 备份位置:`/nas_vol8/upgrade/backups/dumps/yangca_full_20260426_105359.sql`(127G)。
- 回滚:已恢复旧 PG17 5488;`sentinels.sh 7` 和 `endpoint_check.sh` 已重新 PASS。
- 停机/不一致窗口:约 2026-04-26 15:27:51-15:38:39 Asia/Shanghai,约 11 分钟。
- blocker note:`rb5_bench.notes.topic='upgrade_failed'` 已插入。

## 1. 现状探测(阶段 0)

- 5 台宿主机均为 CentOS Linux 7(Core),kernel 3.10.0 系列。
- 当前生产不是宿主机 rpm/deb 直装,而是 Docker:
  - coordinator 217:`citus-coordinator-5488`,image `citusdata/citus:14.0.0-pg17`,volume `/data/pgsql/17-citus/coordinator/data:/var/lib/postgresql/data`
  - workers 216/219/220/221:`citus-worker-5488`,image `citusdata/citus:14.0.0-pg17`,volume `/data/pgsql/17-citus/worker/data:/var/lib/postgresql/data`
  - PG17 旧基线 5433:`pg17-test`,image `postgres:17`
- 当前生产版本:
  - PostgreSQL 17.6 `(Debian 17.6-2.pgdg13+1)`
  - Citus 14.0-1
  - PostGIS 3.6.3
  - `pg_stat_statements` 1.11
- NAS:`/nas_vol8`,约 200T 总量,探测时约 65T 可用。
- 数据基线:
  - `rb5.trusted_cell_library WHERE batch_id=7` = 340,766
  - `rb5.trusted_cell_library` total = 1,643,078
  - `pg_dist_partition` = 59

## 2. 资源准备(阶段 1)

- Docker Hub/registry 直连不稳定;使用国内镜像 `docker.1ms.run/library/postgres:18-bookworm` 作为 PG18.3 基底。
- 自建目标镜像:
  - `optinet/citus:14.0.0-pg18.3-postgis3.6.3`
  - PostgreSQL 18.3 `(Debian 18.3-1.pgdg12+1)`
  - Citus package `postgresql-18-citus-14.0` 14.0.1.citus-1,extension version 14.0-1
  - PostGIS 3.6.3
- 镜像包:
  - `/nas_vol8/upgrade/packages/images/optinet_citus_14.0.1_pg18.3_postgis3.6.3_20260426_105314.tar.gz`
  - sha256 `1958390449d88385010ad18148cb69a5728117819e4560e406792f90fff92339`

## 3. 单机 spike(阶段 2)

- worker 221 上使用独立容器 `citus-spike-5489`,独立端口 5489,独立数据目录 `/data/pgsql/18-citus-spike-pg183/pgroot`。
- spike 结果:
  - `SELECT version()` = PG 18.3
  - `CREATE EXTENSION citus/postgis/pg_stat_statements` 成功
  - `create_distributed_table('t','id')` 成功
  - 插入 1000 行后 `SELECT count(*)` = 1000
- 发现:官方 `citusdata/citus:latest`/`14.0.0` 为 PG18.1 + Citus,但缺 PostGIS;因此改为 PG18.3 bookworm 基底加 Citus/PostGIS 包。

## 4. 备份(阶段 3)

- `pg_dumpall` 在 217 容器内执行,未停生产:
  - `/nas_vol8/upgrade/backups/dumps/yangca_full_20260426_105359.sql`
  - size 127G
  - start 2026-04-26 10:53:59 +0800
  - end 2026-04-26 11:27:57 +0800
- 配置备份:
  - `/nas_vol8/upgrade/backups/configs/20260426_105359/`
  - 含 5 台 container inspect、`postgresql.conf`、`pg_hba.conf`、`postgresql.auto.conf`

## 5. 正式升级(阶段 4)

- 采用路 B fresh rebuild:
  - 5 台加载目标镜像。
  - 先在 5490 起 PG18/Citus/PostGIS 新集群。
  - `pg_dumpall` 恢复到 5490,rc=0,耗时约 1h27m。
  - 恢复日志仅有预创建对象导致的重复错误:
    - `role "postgres" already exists`
    - `database "optinet_rebuild5_sandbox" already exists`
    - `database "yangca" already exists`
- 关键偏差:
  - dump 恢复后 `pg_dist_partition=0`,需手工按旧集群 59 个对象重建 Citus 分布元数据。
  - 从旧 5488 抽取 43 个 hash distributed table + 16 个 reference table,在 5490 运行 `create_reference_table` / `create_distributed_table`。
  - 分布重建完成,rc=0,`pg_dist_partition=59`。
- 失败点:
  - 切到 5488 后,PG18 查询 `rb5.trusted_cell_library` 和 `rb5.cell_sliding_window` 正常,但 `rb5.enriched_records` 与 `rb5_stage.step2_input_b7_20251207` 返回 0。
  - `endpoint_check.sh` 在 PG18 5488 上失败:`enriched_7_batch_coverage` FAIL。
  - 判定为新 PG18/Citus 分布式恢复的数据完整性嫌疑,停止升级并回滚。

## 6. 回滚与当前状态

- 回滚动作:
  - 停 PG18 `citus-*-5488-pg18` 容器。
  - 重启原 PG17 `citus-coordinator-5488` 与 4 个 `citus-worker-5488` 容器。
- 当前生产 5488 已恢复:
  - PG 17.6
  - Citus active workers = 4
  - `pg_dist_partition=59`
  - TCL b7 = 340,766
  - `sentinels.sh 7` 4 项 PASS
  - `endpoint_check.sh` 4 项 PASS
- PG18 新数据目录和镜像均保留,用于后续诊断:
  - `/data/pgsql/18-citus/coordinator/pgroot`
  - `/data/pgsql/18-citus/worker/pgroot`
  - `/nas_vol8/upgrade/packages/images/`
  - `/nas_vol8/upgrade/logs/restore_5490_20260426_114619.log`
  - `/nas_vol8/upgrade/logs/recreate_distribution_5490_20260426_132519.log`

## 7. 已知限制 / 未做

- 未完成 PG18 生产切换。
- 未执行阶段 6 调优到生产,因为生产已回滚 PG17。
- 未清理 PG18 `create_distributed_table` 提示的 local hidden data,保留现场供后续诊断。
- 未删除任何 PG17 旧数据或备份。

## 8. fallback 路径

- 当前 fallback 已执行:原 PG17 Docker 容器重新承载 5488。
- 如需再次尝试 PG18,建议先不要复用 `pg_dumpall` 直接整库恢复 + 手工 `create_distributed_table` 的方式;应改为:
  - 用 Citus 官方推荐的 distributed backup/restore 流程,或
  - 分 schema/data/metadata 分阶段恢复,每个 distributed table 在创建分布后用 per-table COPY 导入并逐表校验,或
  - 对非关键 stage 表选择 reset 后重跑而非强行恢复。
- 跨版本兜底 dump 仍在 NAS:
  - `/nas_vol8/upgrade/backups/dumps/yangca_full_20260426_105359.sql`
