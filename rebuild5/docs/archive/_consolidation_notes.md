# consolidation notes

## 2026-04-28

### doc_consolidation_phase0_done

- scope: `rebuild5/docs/`
- inventory_rows: 161
- category_counts:
  - authority = 6
  - core13 = 13
  - archive_dirs = 130
  - archive_top_files = 9
  - active_gps1 = 2
  - prompt_final_archive = 1
- outdated_hits: 39
- outdated_hit_files:
  - `rebuild5/docs/05_画像维护.md` = 2
  - `rebuild5/docs/11_核心表说明.md` = 37
- link_hits: 104
- notes:
  - `PROJECT_STATUS.md` / `CLUSTER_USAGE.md` / `runbook.md` / `README.md` 是阶段 2 的主要修链对象。
  - `11_核心表说明.md` 是阶段 3 的最高风险文档,表名前缀更新必须保守执行。
  - grep/link 验证阶段都必须排除 `DOC_CONSOLIDATION_PROMPT.md` 自身。

### doc_consolidation_phase1_done

- moved_top_level_dirs: 12
- moved_top_level_files: 9
- historical_markdown_frozen: 139
- archive_readme_added: `rebuild5/docs/archive/README.md`
- notes:
  - `fix/ fix1/ fix2/ fix3/ fix4/ fix5/ fix6_optim/ loop_optim/ upgrade/ dev/ human_guide/ gps研究/` 已物理移入 `archive/`
  - `rerun_delivery_* / 重跑* / 样例速度优化* / 速度优化评估* / runbook_v5.md` 已移入 `archive/`
  - `gps1/` 保持顶层 active; `DOC_CONSOLIDATION_PROMPT.md` 保留到阶段 7 再归档

### doc_consolidation_phase2_done

- link_hits_before: 11
- link_hits_after: 0
- files_updated:
  - `rebuild5/docs/PROJECT_STATUS.md`
  - `rebuild5/docs/CLUSTER_USAGE.md`
  - `rebuild5/docs/runbook.md`
  - `rebuild5/docs/README.md`
- notes:
  - 只修 active 区域对 `fix* / fix6_optim / loop_optim / upgrade / runbook_v5` 的链接
  - `archive/` 内部链接保持冷冻态,未修
  - 验证 grep 显式排除了 `DOC_CONSOLIDATION_PROMPT.md`

### doc_consolidation_phase3_done

- core_docs_reviewed: 13
- lines_changed_total: 312
- lines_added: 183
- lines_deleted: 129
- explicit_second_review_flags:
  - `rebuild5/docs/06_服务层_运营商数据库与分析服务.md` — `rebuild4_meta.lac_location_snapshot` 长期口径待 user 二审
- notes:
  - 13 篇核心开发文档已统一补文首“更新声明”
  - 只改 A-D 类内容:环境前置、schema/SQL 示例、量化口径、archive 路径
  - `11_核心表说明.md` 已从旧 `rebuild5.* / rebuild5_meta.* / rebuild5_tmp.*` 对齐到当前 `rb5.* / rb5_meta.* / rb5_stage.*`

### doc_consolidation_phase4_done

- file_rewritten: `rebuild5/docs/README.md`
- navigation_mode: flat
- notes:
  - 顶层 README 已从旧时代长文混排改为扁平导航入口
  - README 只保留入口职责;业务规则、状态机、术语和操作细节下沉到权威文档

### doc_consolidation_phase5_done

- authority_files_aligned:
  - `rebuild5/docs/README.md`
  - `rebuild5/docs/PROJECT_STATUS.md`
  - `rebuild5/docs/CLUSTER_USAGE.md`
  - `rebuild5/docs/runbook.md`
  - `rebuild5/docs/处理流程总览.md`
  - `rebuild5/docs/术语对照表.md`
- files_changed_this_phase:
  - `rebuild5/docs/PROJECT_STATUS.md`
  - `rebuild5/docs/runbook.md`
- notes:
  - `PROJECT_STATUS.md` 已把“当前 active 的事”改到 2026-04-28 口径,移除过时的 216 待执行表述
  - `runbook.md` 已对齐最终内核升级状态,并统一复用脚本名为 `install_kernel_on_node.sh`
  - `CLUSTER_USAGE.md` / `处理流程总览.md` / `术语对照表.md` 本阶段只做对齐复核,正文无需再改

### doc_consolidation_phase6_done

- verification_scans:
  - legacy_cross_reference_links = 0
  - outdated_env_and_schema_keywords = 0
  - legacy_meta_or_tmp_schema = 0
  - direct_runbook_v5_reference = 0
- notes:
  - 4 条 grep 扫描均显式排除了 `DOC_CONSOLIDATION_PROMPT.md`
  - `archive/` 冷冻区未纳入修复或残留判定
