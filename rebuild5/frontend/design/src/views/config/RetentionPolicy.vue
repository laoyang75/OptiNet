<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import PageHeader from '../../components/common/PageHeader.vue'
import { getSystemConfig, type SystemConfigPayload } from '../../api/system'

function toRecord(value: unknown): Record<string, any> {
  return value && typeof value === 'object' ? value as Record<string, any> : {}
}

const config = ref<SystemConfigPayload>({
  current_version: { dataset_key: 'sample_6lac', run_id: '', snapshot_version: 'v0', status: 'completed', updated_at: '' },
  datasets: [],
  params: {},
})

const retention = computed(() => toRecord(config.value.params.retention))
const waiting = computed(() => toRecord(retention.value.waiting))
const dormant = computed(() => toRecord(retention.value.dormant))
const retired = computed(() => toRecord(retention.value.retired))

onMounted(async () => {
  try {
    config.value = await getSystemConfig()
  } catch {
    config.value = { ...config.value }
  }
})
</script>

<template>
  <PageHeader title="数据保留策略" description="waiting 清理、dormant 管理、retired 退出规则。当前为只读展示。">
    <div class="text-xs text-secondary">
      当前版本 {{ config.current_version.snapshot_version }} ｜ 最近运行 {{ config.current_version.run_id || '-' }}
    </div>
  </PageHeader>

  <div class="grid grid-3 gap-lg mb-lg">
    <div class="card">
      <div class="font-semibold text-sm mb-md" style="color:var(--c-waiting)">等待态清理</div>
      <ul class="policy-list">
        <li><span class="label">对象范围</span><span>lifecycle_state = waiting</span></li>
        <li><span class="label">清理触发</span><span>连续 {{ waiting.max_inactive_batches ?? 0 }} 批无新观测</span></li>
        <li><span class="label">清理动作</span><span>从评估池移除，保留注册记录</span></li>
        <li><span class="label">阈值来源</span><span class="tag" style="background:#dcfce7;color:#166534">已外化</span></li>
      </ul>
    </div>

    <div class="card">
      <div class="font-semibold text-sm mb-md" style="color:var(--c-dormant)">休眠管理</div>
      <ul class="policy-list">
        <li><span class="label">对象范围</span><span>qualified+ 对象</span></li>
        <li><span class="label">触发条件</span><span>连续 {{ dormant.max_inactive_batches ?? 0 }} 批无新数据</span></li>
        <li><span class="label">状态变化</span><span>→ dormant，暂停活跃维护</span></li>
        <li><span class="label">恢复条件</span><span>再次出现新数据时恢复</span></li>
        <li><span class="label">阈值来源</span><span class="tag" style="background:#dcfce7;color:#166534">已外化</span></li>
      </ul>
    </div>

    <div class="card">
      <div class="font-semibold text-sm mb-md" style="color:var(--c-retired)">退出管理</div>
      <ul class="policy-list">
        <li><span class="label">对象范围</span><span>dormant 对象</span></li>
        <li><span class="label">触发条件</span><span>持续静默超过 {{ retired.max_inactive_batches ?? 0 }} 批</span></li>
        <li><span class="label">状态变化</span><span>→ retired，退出可信赖库</span></li>
        <li><span class="label">重新激活</span><span>回到 Step 2 重新积累证据</span></li>
        <li><span class="label">阈值来源</span><span class="tag" style="background:#dcfce7;color:#166534">已外化</span></li>
      </ul>
    </div>
  </div>

  <div class="card">
    <div class="font-semibold text-sm mb-sm">生命周期退出说明</div>
    <ul class="text-xs text-secondary" style="padding-left:18px;line-height:2">
      <li>退出链路：qualified+ → dormant → retired</li>
      <li>retired 对象再次出现时，不恢复旧状态，而是重新从 waiting 开始积累</li>
      <li>全部批次阈值已外化到 <code>retention_params.yaml</code>，页面展示的是当前生效值</li>
      <li>BS / LAC 的退出由下层联动触发</li>
    </ul>
  </div>
</template>

<style scoped>
.policy-list { list-style: none; padding: 0; font-size: 12px; }
.policy-list li {
  display: flex;
  justify-content: space-between;
  padding: 6px 0;
  border-bottom: 1px solid var(--c-border-light);
}
.policy-list li:last-child { border-bottom: none; }
.policy-list .label { color: var(--c-text-muted); flex-shrink: 0; width: 80px; }
code { font-family: var(--font-mono); font-size: 11px; background: var(--c-bg); padding: 1px 4px; border-radius: 3px; }
</style>
