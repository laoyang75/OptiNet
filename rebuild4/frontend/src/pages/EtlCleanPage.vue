<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getEtlCleanStats } from '../lib/api'
import EtlFooter from '../components/EtlFooter.vue'

const loading = ref(true)
const data = ref<any>(null)

function fmt(n: any) { return typeof n === 'number' ? n.toLocaleString() : (n ?? '-') }
function pct(n: number, total: number) { return total > 0 ? (n / total * 100).toFixed(3) + '%' : '-' }

const catColors: Record<string, string> = { '运营商': '#3b82f6', 'LAC': '#f59e0b', 'CellID': '#ef4444', '信号': '#8b5cf6', '位置': '#10b981', 'WiFi': '#6b7280' }

onMounted(async () => {
  try { data.value = (await getEtlCleanStats()).data } catch {}
  finally { loading.value = false }
})
</script>

<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">4. 清洗</h2>
        <p class="page-desc">对解析后的数据逐条执行清洗规则。无效字段置 NULL，无效 CellID 行删除。</p>
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
        <div class="section-title">清洗流水线</div>
        <div class="pipeline-flow">
          <div class="flow-box">
            <div class="flow-label">解析后</div>
            <div class="flow-value">{{ fmt(data.input) }}</div>
          </div>
          <div class="flow-arrow">→</div>
          <div class="flow-box accent">
            <div class="flow-label">清洗后</div>
            <div class="flow-value">{{ fmt(data.output) }}</div>
          </div>
          <div class="flow-deleted">删除 {{ fmt(data.deleted) }} 条无效 CellID 行</div>
        </div>
        <div class="run-info">scope: {{ data.scope }} · 执行时间: {{ data.run_at }}</div>
      </div>

      <div class="section" v-if="data.rules && data.rules.length">
        <div class="section-title">清洗规则明细（{{ data.rules.length }} 条）</div>
        <table class="tbl">
          <thead><tr><th>ID</th><th>类别</th><th>规则</th><th>字段</th><th>动作</th><th>违规数</th><th>违规率</th></tr></thead>
          <tbody>
            <tr v-for="r in data.rules" :key="r.id">
              <td>{{ r.id }}</td>
              <td><span class="badge" :style="{ background: (catColors[r.cat] || '#6b7280') + '20', color: catColors[r.cat] || '#6b7280' }">{{ r.cat }}</span></td>
              <td>{{ r.name }}</td>
              <td><code>{{ r.field }}</code></td>
              <td><span class="action-tag" :class="r.action">{{ r.action }}</span></td>
              <td :style="{ fontWeight: 700, color: r.violations > 0 ? '#b45309' : '#059669' }">{{ fmt(r.violations) }}</td>
              <td>{{ pct(r.violations, data.input) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="section">
        <div class="note">
          清洗方式：字段级置 NULL（保留行），最终删除无有效 CellID 的行。
          规则独立定义，可单独增删。对齐 rebuild2 exec_l0_gps.sql L217-278。
        </div>
      </div>

      <EtlFooter code-path="rebuild4/backend/app/etl/pipeline.py → step2_clean(), ODS_RULES" doc-path="rebuild4/docs/01_etl/02_清洗.md" />
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
.flow-box.accent { background: #f0fdf4; border-color: #22c55e; }
.flow-label { font-size: 11px; color: var(--text); }
.flow-value { font-size: 22px; font-weight: 700; color: var(--text-h); }
.flow-arrow { font-size: 20px; font-weight: 700; color: var(--text); }
.flow-deleted { font-size: 13px; font-weight: 600; color: #dc2626; margin-left: 8px; }
.tbl { width: 100%; border-collapse: collapse; font-size: 12.5px; }
.tbl th { text-align: left; padding: 6px 8px; border-bottom: 2px solid var(--border); font-weight: 600; font-size: 11px; color: var(--text); }
.tbl td { padding: 5px 8px; border-bottom: 1px solid var(--border); color: var(--text-h); }
.badge { display: inline-block; padding: 1px 7px; border-radius: 10px; font-size: 10.5px; font-weight: 600; }
.action-tag { font-size: 10px; font-weight: 600; padding: 1px 6px; border-radius: 8px; }
.action-tag.nullify { background: #fef3c7; color: #92400e; }
.action-tag.flag_gps { background: #dbeafe; color: #1d4ed8; }
.action-tag.nullify_custom { background: #f3f4f6; color: #6b7280; }
.note { font-size: 12px; color: var(--text); background: var(--social-bg); padding: 10px 14px; border-radius: 6px; line-height: 1.6; }
</style>
