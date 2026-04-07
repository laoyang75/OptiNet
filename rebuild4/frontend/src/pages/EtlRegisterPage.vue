<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { getFoundationRawOverview } from '../lib/api'
import EtlFooter from '../components/EtlFooter.vue'

const loading = ref(true)
const error = ref('')
const data = ref<any>({})

const decisionLabel: Record<string, string> = { keep: '保留', parse: '解析', drop: '丢弃' }
const decisionClass: Record<string, string> = { keep: 'dec-keep', parse: 'dec-parse', drop: 'dec-drop' }
const categoryColors: Record<string, string> = { '标识': '#3b82f6', '时间': '#f59e0b', '元数据': '#6b7280', '网络': '#10b981', '位置': '#ef4444', '核心': '#8b5cf6' }

const fields = computed(() => data.value.fields || [])
const summary = computed(() => data.value.decision_summary || {})
const sources = computed(() => data.value.source_tables || [])

onMounted(async () => {
  try { data.value = (await getFoundationRawOverview()).data || {} }
  catch (e: any) { error.value = e.message || '加载失败' }
  finally { loading.value = false }
})
</script>

<template>
  <div class="page">
    <h2 class="page-title">1. 数据源注册</h2>
    <p class="page-desc">注册原始数据源表和字段。定义 27 列中哪些保留、哪些需要解析、哪些丢弃。</p>

    <div v-if="loading" class="loading">加载中…</div>
    <div v-else-if="error" class="loading err">{{ error }}</div>
    <template v-else>
      <div class="section">
        <div class="section-title">数据源表</div>
        <div class="source-cards">
          <div class="source-card" v-for="s in sources" :key="s.name">
            <div class="source-schema">{{ s.schema }}</div>
            <div class="source-name">{{ s.name }}</div>
            <div class="source-meta">{{ s.columns }} 列</div>
            <div v-if="s.sample_rows != null" class="source-meta">样本: <strong>{{ s.sample_table }}</strong>（{{ s.sample_rows?.toLocaleString() }} 条）</div>
          </div>
        </div>
      </div>

      <div class="section">
        <div class="section-title">决策进度（{{ data.field_count }} 列）</div>
        <div class="chip-bar">
          <div v-for="(count, key) in summary" :key="key" class="chip" :class="decisionClass[key as string]">
            <span>{{ decisionLabel[key as string] || key }}</span>
            <strong>{{ count }}</strong>
          </div>
        </div>
      </div>

      <div class="section">
        <div class="section-title">字段清单</div>
        <table class="tbl">
          <thead><tr><th>#</th><th>字段名</th><th>分类</th><th>说明</th><th>类型</th><th>决策</th></tr></thead>
          <tbody>
            <tr v-for="f in fields" :key="f.seq">
              <td>{{ f.seq }}</td>
              <td><strong>{{ f.name }}</strong></td>
              <td><span class="badge" :style="{ background: categoryColors[f.category] || '#6b7280', color: '#fff' }">{{ f.category }}</span></td>
              <td>{{ f.desc }}</td>
              <td><code>{{ f.type }}</code></td>
              <td><span class="badge" :class="decisionClass[f.decision]">{{ decisionLabel[f.decision] }}</span></td>
            </tr>
          </tbody>
        </table>
      </div>

      <EtlFooter code-path="rebuild4/backend/app/routers/governance_foundation.py → raw-overview" doc-path="rebuild4/prompts/00a_ETL管道设计.md" />
    </template>
  </div>
</template>

<style scoped>
.page { max-width: 980px; margin: 0 auto; padding: 24px 16px; }
.page-title { font-size: 20px; font-weight: 700; color: var(--text-h); margin: 0 0 4px; }
.page-desc { font-size: 13px; color: var(--text); margin: 0 0 20px; }
.loading { text-align: center; padding: 48px; color: var(--text); }
.loading.err { color: var(--red-600); }
.section { margin-bottom: 24px; }
.section-title { font-size: 15px; font-weight: 700; color: var(--text-h); margin-bottom: 10px; }
.source-cards { display: flex; gap: 12px; }
.source-card { background: var(--bg); border: 1px solid var(--border); border-radius: 8px; padding: 12px 16px; flex: 1; }
.source-schema { font-size: 11px; color: var(--text); }
.source-name { font-size: 12px; font-weight: 600; color: var(--text-h); word-break: break-all; margin-top: 2px; }
.source-meta { font-size: 12px; color: var(--text); margin-top: 4px; }
.chip-bar { display: flex; gap: 10px; }
.chip { display: flex; align-items: center; gap: 6px; padding: 5px 14px; border-radius: 16px; font-size: 13px; }
.dec-keep { background: #dbeafe; color: #1d4ed8; }
.dec-parse { background: #ede9fe; color: #6d28d9; }
.dec-drop { background: #fee2e2; color: #991b1b; }
.tbl { width: 100%; border-collapse: collapse; font-size: 13px; }
.tbl th { text-align: left; padding: 7px 8px; border-bottom: 2px solid var(--border); font-weight: 600; font-size: 11px; color: var(--text); }
.tbl td { padding: 6px 8px; border-bottom: 1px solid var(--border); color: var(--text-h); }
.badge { display: inline-block; padding: 1px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; }
</style>
