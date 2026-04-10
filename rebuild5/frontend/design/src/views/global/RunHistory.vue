<script setup lang="ts">
import { onMounted, ref } from 'vue'

import PageHeader from '../../components/common/PageHeader.vue'
import { getRunLog, type RunLogItem } from '../../api/system'

const runs = ref<RunLogItem[]>([])
const expandedRunId = ref<string | null>(null)

const statusStyle: Record<string, string> = {
  published: 'background:#dcfce7;color:#166534',
  completed: 'background:#dbeafe;color:#1e40af',
  running: 'background:#fef9c3;color:#854d0e',
  failed: 'background:#fee2e2;color:#991b1b',
  partial: 'background:#fff7ed;color:#9a3412',
}

const runTypeLabel: Record<string, string> = {
  bootstrap: '初始化',
  step1: 'Step 1 ETL',
  pipeline: '完整运行',
  rerun: '参数重跑',
  daily: '日常运行',
  replay: '局部重算',
}

function displayTime(value: string | null | undefined): string {
  if (!value) return '-'
  return value.replace('T', ' ').slice(0, 19)
}

function toggleExpand(runId: string) {
  expandedRunId.value = expandedRunId.value === runId ? null : runId
}

function formatSummaryValue(value: unknown): string {
  if (value === null || value === undefined) return '-'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

onMounted(async () => {
  try {
    const payload = await getRunLog()
    runs.value = payload.runs
  } catch {
    runs.value = []
  }
})
</script>

<template>
  <PageHeader title="运行历史" description="查看所有运行记录、控制操作和发布状态。当前版本仅把历史用于审计与追溯，不支持从此页面切换数据集。" />

  <div class="card" style="padding:0;overflow:auto">
    <table class="data-table">
      <thead>
        <tr>
          <th style="width:28px"></th>
          <th>运行批次</th>
          <th>类型</th>
          <th>数据集</th>
          <th>快照版本</th>
          <th>状态</th>
          <th>开始时间</th>
          <th>结束时间</th>
          <th>步骤链</th>
        </tr>
      </thead>
      <tbody>
        <template v-for="run in runs" :key="run.run_id">
          <tr class="run-row" @click="toggleExpand(run.run_id)">
            <td class="expand-cell">
              <span class="expand-icon" :class="{ expanded: expandedRunId === run.run_id }">›</span>
            </td>
            <td class="font-mono font-semibold">{{ run.run_id }}</td>
            <td>{{ runTypeLabel[run.run_type] || run.run_type }}</td>
            <td class="font-mono">{{ run.dataset_key }}</td>
            <td class="font-mono">{{ run.snapshot_version || '-' }}</td>
            <td><span class="tag" :style="statusStyle[run.status] || statusStyle.completed">{{ run.status }}</span></td>
            <td class="text-sm text-secondary">{{ displayTime(run.started_at) }}</td>
            <td class="text-sm text-secondary">{{ displayTime(run.finished_at) }}</td>
            <td class="font-mono text-xs">{{ run.step_chain || '-' }}</td>
          </tr>
          <tr v-if="expandedRunId === run.run_id && run.result_summary" class="summary-row">
            <td colspan="9">
              <div class="result-summary">
                <div v-for="(value, key) in run.result_summary" :key="key" class="summary-item">
                  <span class="text-muted">{{ key }}</span>
                  <span class="font-mono">{{ formatSummaryValue(value) }}</span>
                </div>
                <div v-if="Object.keys(run.result_summary).length === 0" class="text-muted text-xs">无结果摘要</div>
              </div>
            </td>
          </tr>
          <tr v-if="expandedRunId === run.run_id && !run.result_summary" class="summary-row">
            <td colspan="9">
              <div class="result-summary text-muted text-xs">该运行无结果摘要</div>
            </td>
          </tr>
        </template>
        <tr v-if="runs.length === 0">
          <td colspan="9" class="text-center text-secondary" style="padding:20px">暂无运行记录</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.run-row {
  cursor: pointer;
}
.run-row:hover {
  background: var(--c-bg);
}
.expand-cell {
  text-align: center;
  padding: 0 4px !important;
}
.expand-icon {
  display: inline-block;
  font-size: 14px;
  color: var(--c-text-muted);
  transition: transform 0.15s;
}
.expand-icon.expanded {
  transform: rotate(90deg);
}
.summary-row td {
  padding: 0 !important;
  background: var(--c-bg);
}
.result-summary {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: var(--sp-sm) var(--sp-lg);
  padding: var(--sp-md) var(--sp-lg);
}
.summary-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 12px;
}
</style>
