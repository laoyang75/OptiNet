<script setup lang="ts">
defineProps<{ anchorable?: boolean; baselineEligible?: boolean }>()
</script>
<template>
  <span class="qual-tags">
    <span class="qual-tag" :class="anchorable ? 'yes' : 'no'">{{ anchorable ? '&#10003;' : '&#10007;' }} anchorable</span>
    <span class="qual-tag" :class="baselineEligible ? 'yes' : 'no'">{{ baselineEligible ? '&#10003;' : '&#10007;' }} baseline</span>
  </span>
</template>
<style scoped>
.qual-tags { display: inline-flex; gap: 4px; }
.qual-tag { display: inline-block; padding: 1px 6px; border-radius: var(--radius-sm); font-size: 10px; font-weight: 500; }
.qual-tag.yes { background: var(--green-50); color: var(--green-600); }
.qual-tag.no { background: var(--gray-100); color: var(--gray-400); }
</style>
