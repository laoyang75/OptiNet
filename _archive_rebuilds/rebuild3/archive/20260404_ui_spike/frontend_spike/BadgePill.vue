<template>
  <span class="badge-pill" :class="`badge-pill--${tone}`">
    <slot>{{ label }}</slot>
  </span>
</template>

<script setup lang="ts">
defineProps<{
  label?: string;
  tone: 'blue' | 'green' | 'amber' | 'orange' | 'red' | 'slate' | 'violet';
}>();
</script>

<style scoped>
.badge-pill {
  display: inline-flex;
  align-items: center;
  gap: 0.38rem;
  min-height: 28px;
  padding: 0 0.78rem;
  border-radius: 999px;
  border: 1px solid transparent;
  font-size: 0.76rem;
  font-weight: 700;
  line-height: 1;
  white-space: nowrap;
}

.badge-pill--blue {
  color: var(--blue-strong);
  background: var(--blue-soft);
  border-color: rgba(44, 94, 188, 0.18);
}

.badge-pill--green {
  color: var(--green-strong);
  background: var(--green-soft);
  border-color: rgba(24, 140, 92, 0.18);
}

.badge-pill--amber {
  color: var(--amber-strong);
  background: var(--amber-soft);
  border-color: rgba(180, 118, 12, 0.2);
}

.badge-pill--orange {
  color: var(--orange-strong);
  background: var(--orange-soft);
  border-color: rgba(189, 100, 21, 0.2);
}

.badge-pill--red {
  color: var(--red-strong);
  background: var(--red-soft);
  border-color: rgba(194, 66, 72, 0.22);
}

.badge-pill--slate {
  color: var(--slate-strong);
  background: var(--slate-soft);
  border-color: rgba(96, 110, 133, 0.22);
}

.badge-pill--violet {
  color: var(--violet-strong);
  background: var(--violet-soft);
  border-color: rgba(121, 93, 176, 0.2);
}
</style>
