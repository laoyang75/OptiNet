<script setup lang="ts">
defineProps<{ state?: string }>()
const colors: Record<string, string> = {
  healthy: 'green', insufficient: 'amber', gps_bias: 'orange', collision_suspect: 'orange',
  collision_confirmed: 'red', dynamic: 'orange', migration_suspect: 'orange',
}
</script>
<template>
  <span v-if="state" class="health-badge" :class="colors[state] || 'gray'">{{ state }}</span>
</template>
<style scoped>
.health-badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 500; }
.green { background: var(--green-50); color: var(--green-600); }
.amber { background: var(--amber-50); color: var(--amber-600); }
.orange { background: var(--orange-50); color: var(--orange-600); }
.red { background: var(--red-50); color: var(--red-600); }
.gray { background: var(--gray-100); color: var(--gray-500); }
</style>
