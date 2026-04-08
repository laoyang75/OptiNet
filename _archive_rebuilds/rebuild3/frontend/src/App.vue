<template>
  <div class="app-shell">
    <aside class="app-sidebar">
      <div class="sidebar-brand">rebuild3</div>
      <nav class="sidebar-nav">
        <!-- 主流程层 -->
        <div class="sidebar-group-label">主流程层</div>
        <RouterLink
          v-for="item in mainItems"
          :key="item.to"
          :to="item.to"
          class="sidebar-link"
          :class="{ 'sidebar-link--active': isNavActive(item.to) }"
        >
          <span class="ico">{{ item.icon }}</span>
          <span>{{ item.label }}</span>
        </RouterLink>
        <div class="sidebar-divider"></div>

        <!-- 画像视角层 -->
        <div class="sidebar-group-label">画像视角层</div>
        <RouterLink
          v-for="item in profileItems"
          :key="item.to"
          :to="item.to"
          class="sidebar-link"
          :class="{ 'sidebar-link--active': isNavActive(item.to) }"
        >
          <span class="ico">{{ item.icon }}</span>
          <span>{{ item.label }}</span>
        </RouterLink>
        <div class="sidebar-divider"></div>

        <!-- 支撑治理层 -->
        <div class="sidebar-group-label">支撑治理层</div>
        <RouterLink
          v-for="item in supportItems"
          :key="item.to"
          :to="item.to"
          class="sidebar-link"
          :class="{ 'sidebar-link--active': isNavActive(item.to) }"
        >
          <span class="ico">{{ item.icon }}</span>
          <span>{{ item.label }}</span>
        </RouterLink>
      </nav>
    </aside>

    <div class="app-main">
      <header class="app-topbar">
        <div class="topbar-title">{{ currentMeta.title }}</div>
        <div class="topbar-status">
          <span class="status-dot" :class="statusDotClass"></span>
          {{ statusText }}
        </div>
      </header>

      <GlobalStatusBar :runtime="runtimeStore" />

      <div class="page-content">
        <main class="page-body">
          <RouterView />
        </main>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue';
import { RouterLink, RouterView, useRoute } from 'vue-router';

import GlobalStatusBar from './components/GlobalStatusBar.vue';
import { useRuntimeStore } from './stores/runtime';

const route = useRoute();
const runtimeStore = useRuntimeStore();

const mainItems = [
  { to: '/flow/overview', label: '流转总览', icon: '◎' },
  { to: '/flow/snapshot', label: '流转快照', icon: '⏲' },
  { to: '/runs', label: '运行/批次中心', icon: '⚙' },
  { to: '/objects', label: '对象浏览', icon: '◼' },
  { to: '/observation', label: '等待/观察工作台', icon: '⏱' },
  { to: '/anomalies', label: '异常工作台', icon: '⚠' },
  { to: '/baseline', label: '基线/画像', icon: '★' },
];

const profileItems = [
  { to: '/profiles/lac', label: 'LAC 画像', icon: '◔' },
  { to: '/profiles/bs', label: 'BS 画像', icon: '◓' },
  { to: '/profiles/cell', label: 'Cell 画像', icon: '■' },
];

const supportItems = [
  { to: '/governance', label: '基础数据治理', icon: '☰' },
  { to: '/compare', label: '验证/对照', icon: '☑' },
  { to: '/initialization', label: '初始化数据', icon: '▶' },
];

const currentMeta = computed(() => {
  const title = typeof route.meta.title === 'string' ? route.meta.title : 'rebuild3 流式治理工作台';
  return { title };
});

const statusDotClass = computed(() => {
  if (runtimeStore.error) return 'status-dot--error';
  if (runtimeStore.loading) return 'status-dot--processing';
  if (runtimeStore.current) return 'status-dot--ok';
  return '';
});

const statusText = computed(() => {
  if (runtimeStore.error) return '上下文异常';
  if (runtimeStore.loading) return '加载中…';
  if (runtimeStore.current) return '运行中';
  return '未连接';
});

function isNavActive(target: string): boolean {
  if (target === '/objects') {
    return route.path.startsWith('/objects');
  }
  return route.path === target;
}

onMounted(() => {
  runtimeStore.loadContext();
});
</script>
