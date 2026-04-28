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
