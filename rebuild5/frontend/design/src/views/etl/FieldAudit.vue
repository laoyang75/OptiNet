<script setup lang="ts">
import { onMounted, ref } from 'vue'

import PageHeader from '../../components/common/PageHeader.vue'
import { apiGet } from '../../api/client'

interface FieldItem {
  name: string
  name_cn: string
  type: string
  source: string
  desc: string
}

interface FieldGroup {
  category: string
  count: number
  fields: FieldItem[]
}

interface AuditPayload {
  total_field_count: number
  raw_field_count: number
  category_summary: Record<string, number>
  groups: FieldGroup[]
}

const totalFields = ref(0)
const rawFields = ref(0)
const categorySummary = ref<Record<string, number>>({})
const groups = ref<FieldGroup[]>([])

const sourceStyle: Record<string, string> = {
  '直接映射': 'background:#dcfce7;color:#166534',
  '解析提取': 'background:#fef3c7;color:#92400e',
  '计算派生': 'background:#dbeafe;color:#1e40af',
  '标签': 'background:#e0e7ff;color:#3730a3',
  '自动生成': 'background:#f3e8ff;color:#6b21a8',
}

const catColor: Record<string, string> = {
  '标识': '#6366f1', '来源': '#8b5cf6', '解析': '#f59e0b',
  '补齐': '#10b981', '网络': '#3b82f6', '信号': '#ef4444',
  '时间': '#06b6d4', '位置': '#22c55e', '元数据': '#6b7280',
}

onMounted(async () => {
  try {
    const payload = await apiGet<AuditPayload>('/api/etl/field-audit')
    totalFields.value = payload.total_field_count
    rawFields.value = payload.raw_field_count
    categorySummary.value = payload.category_summary
    groups.value = payload.groups
  } catch {
    groups.value = []
  }
})
</script>

<template>
  <PageHeader title="字段定义" :description="`当前页展示 Step 1 冻结字段定义与目标结构（${rawFields} 列原始 → ${totalFields} 个目标字段），不代表实时源表覆盖率审计。`" />

  <div class="category-grid mb-lg">
    <div v-for="(count, cat) in categorySummary" :key="cat" class="cat-chip">
      <span class="cat-label" :style="{ color: catColor[cat] || '#6b7280' }">{{ cat }}</span>
      <span class="cat-count">{{ count }}</span>
    </div>
  </div>

  <div v-for="g in groups" :key="g.category" class="field-group mb-lg">
    <h3 class="group-title">
      <span class="cat-badge" :style="{ background: catColor[g.category] || '#6b7280' }">{{ g.category }}</span>
      {{ g.category }}字段（{{ g.count }}）
    </h3>
    <div class="card" style="padding:0;overflow:auto">
      <table class="data-table">
        <thead>
          <tr>
            <th>字段名</th>
            <th>中文名</th>
            <th>类型</th>
            <th>来源</th>
            <th>说明</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="f in g.fields" :key="f.name">
            <td><code class="field-name">{{ f.name }}</code></td>
            <td>{{ f.name_cn }}</td>
            <td><code class="type-tag">{{ f.type }}</code></td>
            <td><span class="tag" :style="sourceStyle[f.source] || ''">{{ f.source }}</span></td>
            <td class="text-sm text-secondary">{{ f.desc }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.category-grid {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-md);
}
.cat-chip {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 64px;
}
.cat-label { font-size: 11px; font-weight: 600; }
.cat-count { font-size: 22px; font-weight: 700; color: var(--c-text); }
.group-title {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: var(--sp-sm);
  display: flex;
  align-items: center;
  gap: var(--sp-sm);
}
.cat-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  color: #fff;
  font-size: 11px;
  font-weight: 600;
}
.field-name {
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 600;
}
.type-tag {
  font-family: var(--font-mono);
  font-size: 11px;
  background: var(--c-bg);
  padding: 1px 4px;
  border-radius: 3px;
}
</style>
