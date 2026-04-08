<template>
  <span class="badge" :class="badgeClass">
    <span class="badge-icon">{{ icon }}</span>
    {{ label }}
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{
  state: string;
}>();

const CONFIG: Record<string, { label: string; icon: string; cls: string }> = {
  healthy:              { label: '健康',     icon: '✓', cls: 'badge-healthy' },
  insufficient:         { label: '证据不足', icon: '?', cls: 'badge-insufficient' },
  gps_bias:             { label: 'GPS偏差',  icon: '⊕', cls: 'badge-gps-bias' },
  collision_suspect:    { label: '碰撞嫌疑', icon: '△', cls: 'badge-collision-suspect' },
  collision_confirmed:  { label: '碰撞确认', icon: '⊘', cls: 'badge-collision-confirmed' },
  dynamic:              { label: '动态',     icon: '→', cls: 'badge-dynamic' },
  migration_suspect:    { label: '迁移嫌疑', icon: '⇢', cls: 'badge-migration' },
};

const config = computed(() => CONFIG[props.state] || { label: props.state, icon: '?', cls: 'badge-insufficient' });
const label = computed(() => config.value.label);
const icon = computed(() => config.value.icon);
const badgeClass = computed(() => config.value.cls);
</script>
