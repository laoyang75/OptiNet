<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getEtlParseStats } from '../lib/api'
import EtlFooter from '../components/EtlFooter.vue'

const loading = ref(true)
const data = ref<any>(null)

function fmt(n: any) { return typeof n === 'number' ? n.toLocaleString() : (n ?? '-') }

onMounted(async () => {
  try { data.value = (await getEtlParseStats()).data } catch {}
  finally { loading.value = false }
})
</script>

<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">3. 解析（炸开）</h2>
        <p class="page-desc">原始记录的 cell_infos (JSON) 和 ss1 (文本) 拆解为多行结构化数据。一条原始记录 → 多条 L0 记录。</p>
      </div>
      <div class="scope-select">
        <label>Scope</label>
        <select :value="data?.scope || 'sample'">
          <option value="sample">sample</option>
        </select>
      </div>
    </div>

    <div v-if="loading" class="loading">加载中…</div>
    <div v-else-if="!data" class="loading">ETL 未执行，暂无数据。</div>
    <template v-else>

      <div class="section">
        <div class="section-title">解析流水线</div>
        <div class="pipeline-flow">
          <div class="flow-box">
            <div class="flow-label">原始记录</div>
            <div class="flow-value">{{ fmt(data.raw_input) }}</div>
          </div>
          <div class="flow-arrow">→</div>
          <div class="flow-box accent">
            <div class="flow-label">解析后</div>
            <div class="flow-value">{{ fmt(data.parsed_output) }}</div>
          </div>
          <div class="flow-ratio">扩展比 {{ data.expansion_ratio }}x</div>
        </div>
        <div class="run-info">scope: {{ data.scope }} · 执行时间: {{ data.run_at }}</div>
      </div>

      <div class="section">
        <div class="section-title">来源分布</div>
        <table class="tbl">
          <thead><tr><th>来源</th><th>行数</th><th>说明</th></tr></thead>
          <tbody>
            <tr><td><span class="badge badge-blue">cell_infos GPS</span></td><td>{{ fmt(data.ci_gps) }}</td><td>GPS 表 cell_infos JSON 解析</td></tr>
            <tr><td><span class="badge badge-blue">cell_infos LAC</span></td><td>{{ fmt(data.ci_lac) }}</td><td>LAC 表 cell_infos JSON 解析</td></tr>
            <tr><td><span class="badge badge-orange">ss1 GPS</span></td><td>{{ fmt(data.ss1_gps) }}</td><td>GPS 表 ss1 文本解析</td></tr>
            <tr><td><span class="badge badge-orange">ss1 LAC</span></td><td>{{ fmt(data.ss1_lac) }}</td><td>LAC 表 ss1 文本解析</td></tr>
          </tbody>
        </table>
      </div>

      <EtlFooter code-path="rebuild4/backend/app/etl/pipeline.py → step1_parse()" doc-path="rebuild4/docs/01_etl/01_解析.md" />
    </template>
  </div>
</template>

<style scoped>
.page { max-width: 980px; margin: 0 auto; padding: 24px 16px; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 20px; }
.page-title { font-size: 20px; font-weight: 700; color: var(--text-h); margin: 0 0 4px; }
.page-desc { font-size: 13px; color: var(--text); margin: 0; }
.scope-select { display: flex; align-items: center; gap: 8px; }
.scope-select label { font-size: 12px; font-weight: 600; color: var(--text); }
.scope-select select { font-size: 13px; padding: 4px 10px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg); color: var(--text-h); }
.loading { text-align: center; padding: 48px; color: var(--text); }
.section { margin-bottom: 24px; }
.section-title { font-size: 15px; font-weight: 700; color: var(--text-h); margin-bottom: 10px; }
.run-info { font-size: 11px; color: var(--text); margin-top: 8px; }
.pipeline-flow { display: flex; align-items: center; gap: 12px; padding: 16px; background: var(--code-bg); border-radius: 8px; flex-wrap: wrap; }
.flow-box { text-align: center; padding: 10px 16px; background: var(--bg); border: 1px solid var(--border); border-radius: 8px; }
.flow-box.accent { background: #eff6ff; border-color: #3b82f6; }
.flow-label { font-size: 11px; color: var(--text); }
.flow-value { font-size: 22px; font-weight: 700; color: var(--text-h); }
.flow-arrow { font-size: 20px; font-weight: 700; color: var(--text); }
.flow-ratio { font-size: 14px; font-weight: 700; color: #2563eb; margin-left: 8px; }
.tbl { width: 100%; border-collapse: collapse; font-size: 13px; }
.tbl th { text-align: left; padding: 7px 8px; border-bottom: 2px solid var(--border); font-weight: 600; font-size: 11px; color: var(--text); }
.tbl td { padding: 6px 8px; border-bottom: 1px solid var(--border); color: var(--text-h); }
.badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; }
.badge-blue { background: #dbeafe; color: #1d4ed8; }
.badge-orange { background: #fef3c7; color: #92400e; }
</style>
