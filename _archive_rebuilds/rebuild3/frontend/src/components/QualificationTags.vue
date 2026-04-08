<template>
  <div class="badge-row gap-1">
    <span class="qual-tag" :class="anchorable ? 'qual-true' : 'qual-false'">
      {{ anchorable ? '可锚定' : '不可锚定' }}
    </span>
    <span v-if="showBaseline" class="qual-tag" :class="baselineEligible ? 'qual-true' : 'qual-false'">
      {{ baselineEligible ? '基线合格' : '基线不合格' }}
    </span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{
  anchorable: boolean;
  baselineEligible?: boolean;
  variant?: 'default' | 'lac';
}>();

const showBaseline = computed(() => props.variant !== 'lac' && props.baselineEligible !== undefined);
</script>
