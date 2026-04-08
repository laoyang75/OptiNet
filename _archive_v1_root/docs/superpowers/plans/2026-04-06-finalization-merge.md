# Finalization Merge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge the three finalization agent outputs into the frozen finalization documents and verify that round 1-3 decisions are fully written back.

**Architecture:** Read the upstream merged and decision artifacts first, then synthesize the finalization drafts into canonical merged documents. Freeze the stack, launcher placement, data strategy, and scope boundaries without reopening settled directions.

**Tech Stack:** Markdown, shell (`rg`, `cat`, `python3`), PG17 verification

---

### Task 1: Collect merge inputs

**Files:**
- Read: `rebuild4/docs/02_rounds/round1_plan/merged/01_统一计划.md`
- Read: `rebuild4/docs/02_rounds/round1_plan/merged/02_统一风险与缺口.md`
- Read: `rebuild4/docs/02_rounds/round2_detail/merged/01_统一细化设计.md`
- Read: `rebuild4/docs/02_rounds/round2_detail/merged/02_统一细化校验基线.md`
- Read: `rebuild4/docs/02_rounds/round3_execution/merged/01_统一最终执行任务书.md`
- Read: `rebuild4/docs/02_rounds/round3_execution/merged/02_统一最终校验清单.md`
- Read: `rebuild4/docs/02_rounds/round1_plan/decisions/01_待裁决问题清单.md`
- Read: `rebuild4/docs/02_rounds/round2_detail/decisions/01_待裁决问题清单.md`
- Read: `rebuild4/docs/02_rounds/round3_execution/decisions/01_待裁决问题清单.md`
- Read: `rebuild4/docs/02_rounds/finalization/outputs/codex/*.md`
- Read: `rebuild4/docs/02_rounds/finalization/outputs/claude/*.md`
- Read: `rebuild4/docs/02_rounds/finalization/outputs/gemini/*.md`

- [ ] **Step 1: Inspect the source files**

```bash
find rebuild4/docs/02_rounds -maxdepth 4 -type f | sort
```

- [ ] **Step 2: Read the upstream merged and decision documents**

```bash
cat rebuild4/docs/02_rounds/round1_plan/merged/01_统一计划.md   rebuild4/docs/02_rounds/round1_plan/merged/02_统一风险与缺口.md   rebuild4/docs/02_rounds/round2_detail/merged/01_统一细化设计.md   rebuild4/docs/02_rounds/round2_detail/merged/02_统一细化校验基线.md   rebuild4/docs/02_rounds/round3_execution/merged/01_统一最终执行任务书.md   rebuild4/docs/02_rounds/round3_execution/merged/02_统一最终校验清单.md   rebuild4/docs/02_rounds/round1_plan/decisions/01_待裁决问题清单.md   rebuild4/docs/02_rounds/round2_detail/decisions/01_待裁决问题清单.md   rebuild4/docs/02_rounds/round3_execution/decisions/01_待裁决问题清单.md
```

- [ ] **Step 3: Read the three agents' finalization drafts**

```bash
cat rebuild4/docs/02_rounds/finalization/outputs/codex/01_最终冻结基线草案.md   rebuild4/docs/02_rounds/finalization/outputs/codex/02_最终范围技术栈与数据策略草案.md   rebuild4/docs/02_rounds/finalization/outputs/codex/03_候选裁决问题.md   rebuild4/docs/02_rounds/finalization/outputs/claude/01_最终冻结基线草案.md   rebuild4/docs/02_rounds/finalization/outputs/claude/02_最终范围技术栈与数据策略草案.md   rebuild4/docs/02_rounds/finalization/outputs/claude/03_候选裁决问题.md   rebuild4/docs/02_rounds/finalization/outputs/gemini/01_最终冻结基线草案.md   rebuild4/docs/02_rounds/finalization/outputs/gemini/02_最终范围技术栈与数据策略草案.md   rebuild4/docs/02_rounds/finalization/outputs/gemini/03_候选裁决问题.md
```

### Task 2: Write the canonical merged docs

**Files:**
- Modify: `rebuild4/docs/02_rounds/finalization/merged/01_最终冻结基线.md`
- Modify: `rebuild4/docs/02_rounds/finalization/merged/02_最终技术栈与基础框架约束.md`
- Modify: `rebuild4/docs/02_rounds/finalization/merged/03_数据生成与回灌策略.md`
- Modify: `rebuild4/docs/02_rounds/finalization/merged/04_本轮范围与降级说明.md`
- Modify: `rebuild4/docs/02_rounds/finalization/decisions/01_待裁决问题清单.md`

- [ ] **Step 1: Freeze the baseline**

```text
Write `01_最终冻结基线.md` so it proves round 1-3 and all decisions are fully written back, records the PG17 facts, and lists only the finalization-level closeout fixes.
```

- [ ] **Step 2: Freeze the technical stack and framework boundaries**

```text
Write `02_最终技术栈与基础框架约束.md` so it locks PostgreSQL 17, Python 3.11+ + FastAPI, Vue 3 + TypeScript + Vite, launcher placement, API envelope rules, and explicit prohibitions.
```

- [ ] **Step 3: Freeze the data strategy and scope boundaries**

```text
Write `03_数据生成与回灌策略.md` and `04_本轮范围与降级说明.md` so they define the allowed backfills, real init / rolling rules, trusted-loss naming, compare downgrade, launcher exclusion from G0-G7, and exception-only escalation conditions.
```

### Task 3: Verify consistency

**Files:**
- Verify: `rebuild4/docs/02_rounds/finalization/merged/*.md`
- Verify: `rebuild4/docs/02_rounds/finalization/decisions/01_待裁决问题清单.md`

- [ ] **Step 1: Check headings and non-empty content**

```bash
for f in rebuild4/docs/02_rounds/finalization/merged/*.md rebuild4/docs/02_rounds/finalization/decisions/01_待裁决问题清单.md; do
  echo "## $f"
  rg '^#' "$f"
  test -s "$f"
done
```

- [ ] **Step 2: Check prompt-level requirements are reflected**

```bash
rg -n '冻结|技术栈|数据|范围|降级|启动器|回灌|基线|manifest|裁决'   rebuild4/docs/02_rounds/finalization/merged/*.md   rebuild4/docs/02_rounds/finalization/decisions/01_待裁决问题清单.md
```

- [ ] **Step 3: Review internal consistency**

```text
Confirm the merged docs write back round 1-3 decisions, freeze the stack and data strategy, avoid reopening settled directions, and keep the decision list empty unless one of the three predefined exception classes actually occurs.
```
