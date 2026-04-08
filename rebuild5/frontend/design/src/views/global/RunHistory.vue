<script setup lang="ts">
import PageHeader from '../../components/common/PageHeader.vue'

const runs = [
  { id: 'run_20260408_001', type: '完整运行', dataset: 'sample_6lac', snapshot: 'v3', status: 'published', started: '2026-04-08 14:00', finished: '2026-04-08 18:30', steps: '1→2→3→4→5→6' },
  { id: 'run_20260407_002', type: '局部重算', dataset: 'sample_6lac', snapshot: 'v2', status: 'completed', started: '2026-04-07 10:00', finished: '2026-04-07 12:15', steps: '3→5' },
  { id: 'run_20260406_001', type: '完整运行', dataset: 'sample_6lac', snapshot: 'v1', status: 'completed', started: '2026-04-06 08:00', finished: '2026-04-06 16:45', steps: '1→2→3→4→5→6' },
  { id: 'run_20260401_001', type: '初始化', dataset: 'sample_6lac', snapshot: '-', status: 'completed', started: '2026-04-01 09:00', finished: '2026-04-01 09:30', steps: '1' },
]

const statusStyle: Record<string, string> = {
  published: 'background:#dcfce7;color:#166534',
  completed: 'background:#dbeafe;color:#1e40af',
  running: 'background:#fef9c3;color:#854d0e',
  failed: 'background:#fee2e2;color:#991b1b',
}
</script>

<template>
  <PageHeader title="运行历史" description="查看所有运行记录、控制操作和发布状态。从此页面可跳转到任意步骤的结果页面。" />

  <div class="card" style="padding:0;overflow:auto">
    <table class="data-table">
      <thead>
        <tr>
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
        <tr v-for="run in runs" :key="run.id">
          <td class="font-mono font-semibold">{{ run.id }}</td>
          <td>{{ run.type }}</td>
          <td class="font-mono">{{ run.dataset }}</td>
          <td class="font-mono">{{ run.snapshot }}</td>
          <td><span class="tag" :style="statusStyle[run.status]">{{ run.status === 'published' ? '已发布' : run.status === 'completed' ? '已完成' : run.status }}</span></td>
          <td class="text-sm text-secondary">{{ run.started }}</td>
          <td class="text-sm text-secondary">{{ run.finished }}</td>
          <td class="font-mono text-xs">{{ run.steps }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
