<template>
  <div class="app-shell">
    <header class="shell-topbar">
      <div class="brand-block">
        <p class="kicker">rebuild3 / cell workbench</p>
        <div class="brand-line">
          <h1>Cell 页面先把规则讲清楚</h1>
          <span class="brand-note">精确 / 专业 / 可控</span>
        </div>
        <p class="hero-copy">
          这版不是只给结果，而是把 Cell 过滤、legacy 差异、北京范围、2G/3G 过滤状态和 BS 级联护栏一起摆到页面上。
        </p>
      </div>

      <div class="topbar-aside panel-surface">
        <div>
          <p class="kicker">Visibility First</p>
          <strong class="topbar-metric">对象解释链常驻可见</strong>
        </div>
        <p class="topbar-meta">你最关心的过滤条件，应该在 Cell 页面直接看到，而不是靠翻 SQL。</p>
      </div>
    </header>

    <nav class="route-tabs panel-surface">
      <RouterLink class="route-tab" :class="{ 'route-tab--active': route.name === 'cell-objects' }" :to="{ name: 'cell-objects' }">
        对象浏览
      </RouterLink>
      <RouterLink
        v-if="currentObjectId"
        class="route-tab"
        :class="{ 'route-tab--active': route.name === 'cell-detail' }"
        :to="{ name: 'cell-detail', params: { objectId: currentObjectId } }"
      >
        对象详情
      </RouterLink>
      <RouterLink
        v-if="currentObjectId"
        class="route-tab"
        :class="{ 'route-tab--active': route.name === 'cell-profile' }"
        :to="{ name: 'cell-profile', params: { objectId: currentObjectId } }"
      >
        Cell 画像
      </RouterLink>
    </nav>

    <main class="content-shell">
      <RouterView />
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { RouterLink, RouterView, useRoute } from 'vue-router';

const route = useRoute();

const currentObjectId = computed(() => {
  return typeof route.params.objectId === 'string' ? route.params.objectId : '';
});
</script>
