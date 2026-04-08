<template>
  <span v-if="isWatch" class="watch-badge">WATCH</span>
</template>

<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{
  lifecycleState: string;
  healthState: string;
}>();

const isWatch = computed(() =>
  props.lifecycleState === 'active' && props.healthState !== 'healthy'
);
</script>
