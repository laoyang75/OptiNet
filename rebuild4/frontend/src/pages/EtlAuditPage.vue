<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { getFoundationL0Audit } from '../lib/api'
import EtlFooter from '../components/EtlFooter.vue'

const loading = ref(true)
const error = ref('')
const data = ref<any>({})

const sourceTypeLabel: Record<string, string> = {
  direct: '直接映射', parsed: '解析提取', derived: '计算派生', tag: '标签', generated: '自动生成'
}
const sourceTypeClass: Record<string, string> = {
  direct: 'tag-green', parsed: 'tag-orange', derived: 'tag-blue', tag: 'tag-gray', generated: 'tag-gray'
}
const categoryClass: Record<string, string> = {
  '标识': 'tag-blue', '来源': 'tag-gray', '解析': 'tag-orange', '补齐': 'tag-orange',
  '网络': 'tag-blue', '信号': 'tag-orange', '时间': 'tag-green', '位置': 'tag-green', '元数据': 'tag-gray'
}

// 按 category 分组
const CATEGORY_ORDER = ['标识', '来源', '解析', '补齐', '网络', '信号', '时间', '位置', '元数据']
const groupedFields = computed(() => {
  const fields = data.value.fields || []
  const groups: { category: string; fields: any[] }[] = []
  const map: Record<string, any[]> = {}
  for (const f of fields) {
    if (!map[f.category]) map[f.category] = []
    map[f.category].push(f)
  }
  for (const cat of CATEGORY_ORDER) {
    if (map[cat]) groups.push({ category: cat, fields: map[cat] })
  }
  return groups
})

const catSummary = computed(() => data.value.category_summary || {})

onMounted(async () => {
  try {
    const res = await getFoundationL0Audit()
    data.value = res.data || {}
  } catch (e: any) { error.value = e.message || '加载失败' }
  finally { loading.value = false }
})
</script>

<template>
  <div class="page">
    <h2 class="page-title">2. 字段审计</h2>
    <p class="page-desc">27 列原始字段经 JSON 解析、展开后的目标表结构。共 {{ data.field_count || 0 }} 个字段，按 cell_id 拆行。</p>

    <div v-if="loading" class="empty-state">加载中…</div>
    <div v-else-if="error" class="empty-state" style="color:var(--red-600)">{{ error }}</div>
    <template v-else>

      <!-- 分类统计 stat grid -->
      <div class="stat-grid">
        <div v-for="cat in CATEGORY_ORDER" :key="cat" class="stat-box" v-show="catSummary[cat]">
          <div class="stat-label">{{ cat }}</div>
          <div class="stat-value">{{ catSummary[cat] || 0 }}</div>
        </div>
      </div>

      <!-- 按分类分组卡片 -->
      <div v-for="group in groupedFields" :key="group.category" class="category-card">
        <h3 class="card-heading">
          <span class="tag" :class="categoryClass[group.category]">{{ group.category }}</span>
          {{ group.category }}字段（{{ group.fields.length }}）
        </h3>
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
            <tr v-for="f in group.fields" :key="f.field_name">
              <td><code><strong>{{ f.field_name }}</strong></code></td>
              <td>{{ f.field_name_cn }}</td>
              <td><code class="type-code">{{ f.data_type }}</code></td>
              <td><span class="tag" :class="sourceTypeClass[f.source_type]">{{ sourceTypeLabel[f.source_type] || f.source_type }}</span></td>
              <td class="desc-cell">{{ f.description || '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <EtlFooter code-path="rebuild4/backend/app/routers/governance_foundation.py → l0-audit" doc-path="rebuild4/docs/01_etl/01_解析.md" />

    </template>
  </div>
</template>

<style scoped>
.page { max-width: 1060px; margin: 0 auto; padding: 24px 16px; }
.page-title { font-size: 20px; font-weight: 700; color: var(--text-h); margin: 0 0 4px; }
.page-desc { font-size: 13px; color: var(--text); margin: 0 0 20px; line-height: 1.5; }
.empty-state { text-align: center; padding: 48px 16px; color: var(--text); font-size: 14px; }

/* stat grid */
.stat-grid { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 24px; }
.stat-box { background: var(--bg); border: 1px solid var(--border); border-radius: 8px; padding: 10px 16px; min-width: 80px; text-align: center; }
.stat-label { font-size: 11px; color: var(--text); font-weight: 500; }
.stat-value { font-size: 20px; font-weight: 700; color: var(--text-h); }

/* category card */
.category-card { background: var(--bg); border: 1px solid var(--border); border-radius: 10px; padding: 16px 20px; margin-bottom: 16px; }
.card-heading { font-size: 15px; font-weight: 700; color: var(--text-h); margin: 0 0 12px; display: flex; align-items: center; gap: 8px; }

/* tags */
.tag { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; white-space: nowrap; }
.tag-blue { background: #dbeafe; color: #1d4ed8; }
.tag-green { background: #d1fae5; color: #065f46; }
.tag-orange { background: #fef3c7; color: #92400e; }
.tag-gray { background: #f3f4f6; color: #4b5563; }

/* table */
.data-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.data-table th { text-align: left; padding: 6px 8px; border-bottom: 2px solid var(--border); font-weight: 600; font-size: 11px; color: var(--text); }
.data-table td { padding: 6px 8px; border-bottom: 1px solid var(--border); color: var(--text-h); vertical-align: top; }
.type-code { font-size: 11px; }
.desc-cell { font-size: 12px; color: var(--text); }
</style>
