<script setup lang="ts">
import PageHeader from '../../components/common/PageHeader.vue'
</script>

<template>
  <PageHeader title="数据保留策略" description="waiting 清理、dormant 管理、retired 退出规则。当前为只读展示。" />

  <div class="grid grid-3 gap-lg mb-lg">
    <div class="card">
      <div class="font-semibold text-sm mb-md" style="color:var(--c-waiting)">等待态清理</div>
      <ul class="policy-list">
        <li><span class="label">对象范围</span><span>lifecycle_state = waiting</span></li>
        <li><span class="label">清理触发</span><span>连续 N 批无新观测</span></li>
        <li><span class="label">清理动作</span><span>从评估池移除，保留注册记录</span></li>
        <li><span class="label">阈值状态</span><span class="tag" style="background:#fef9c3;color:#854d0e">待外化</span></li>
      </ul>
    </div>

    <div class="card">
      <div class="font-semibold text-sm mb-md" style="color:var(--c-dormant)">休眠管理</div>
      <ul class="policy-list">
        <li><span class="label">对象范围</span><span>qualified+ 对象</span></li>
        <li><span class="label">触发条件</span><span>连续多批无新数据</span></li>
        <li><span class="label">状态变化</span><span>→ dormant，暂停活跃维护</span></li>
        <li><span class="label">恢复条件</span><span>再次出现新数据时恢复</span></li>
        <li><span class="label">阈值状态</span><span class="tag" style="background:#fef9c3;color:#854d0e">待外化</span></li>
      </ul>
    </div>

    <div class="card">
      <div class="font-semibold text-sm mb-md" style="color:var(--c-retired)">退出管理</div>
      <ul class="policy-list">
        <li><span class="label">对象范围</span><span>dormant 对象</span></li>
        <li><span class="label">触发条件</span><span>持续静默超过退出阈值</span></li>
        <li><span class="label">状态变化</span><span>→ retired，退出可信赖库</span></li>
        <li><span class="label">重新激活</span><span>回到 Step 2 重新积累证据</span></li>
        <li><span class="label">阈值状态</span><span class="tag" style="background:#fef9c3;color:#854d0e">待外化</span></li>
      </ul>
    </div>
  </div>

  <div class="card">
    <div class="font-semibold text-sm mb-sm">生命周期退出说明</div>
    <ul class="text-xs text-secondary" style="padding-left:18px;line-height:2">
      <li>退出链路：qualified+ → dormant → retired</li>
      <li>retired 对象再次出现时，不恢复旧状态，而是重新从 waiting 开始积累</li>
      <li>dormant / retired 的数值阈值尚未外化到 retention_params.yaml，语义已冻结</li>
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
</style>
