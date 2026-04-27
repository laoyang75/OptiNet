<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { getSystemConfig, type CurrentVersion } from '../api/system'
import { mockVersion } from '../mock/data'
import { PAGE_STATUS_LABELS } from '../types'

const route = useRoute()
const collapsed = ref(false)
const currentTitle = computed(() => (route.meta?.title as string) || '')
const version = ref<CurrentVersion>(mockVersion)

interface NavItem { label: string; path: string; group: string }
interface NavSubGroup { subTitle: string; items: NavItem[] }
interface NavSection { title: string; key: string; items?: NavItem[]; subGroups?: NavSubGroup[] }

const navSections: NavSection[] = [
  {
    title: '全局管理', key: 'global',
    items: [
      { label: '数据集选择', path: '/global/dataset', group: 'global' },
      { label: '运行历史', path: '/global/history', group: 'global' },
    ]
  },
  {
    title: '治理控制台', key: 'governance-console',
    subGroups: [
      {
        subTitle: 'Step 1 · 数据源接入',
        items: [
          { label: '数据源注册', path: '/etl/source', group: 'etl' },
          { label: '字段定义', path: '/etl/field-audit', group: 'etl' },
          { label: '解析', path: '/etl/parse', group: 'etl' },
          { label: '清洗', path: '/etl/clean', group: 'etl' },
          { label: 'ODS 规则命中', path: '/etl/rule-stats', group: 'etl' },
          { label: '补齐', path: '/etl/fill', group: 'etl' },
        ]
      },
      {
        subTitle: 'Step 2 · 基础画像与路由',
        items: [
          { label: '基础画像与分流', path: '/profile/routing', group: 'profile' },
        ]
      },
      {
        subTitle: 'Step 3 · 流式质量评估',
        items: [
          { label: '流转总览', path: '/evaluation/overview', group: 'evaluation' },
          { label: 'Cell 流转', path: '/evaluation/cell', group: 'evaluation' },
          { label: 'BS 流转', path: '/evaluation/bs', group: 'evaluation' },
          { label: 'LAC 流转', path: '/evaluation/lac', group: 'evaluation' },
        ]
      },
      {
        subTitle: 'Step 4 · 知识补数',
        items: [
          { label: '知识补数', path: '/governance/fill', group: 'governance' },
        ]
      },
      {
        subTitle: 'Step 5 · 画像维护',
        items: [
          { label: '治理总览', path: '/governance/overview', group: 'governance' },
          { label: 'Cell 维护', path: '/governance/cell', group: 'governance' },
          { label: 'BS 维护', path: '/governance/bs', group: 'governance' },
          { label: 'LAC 维护', path: '/governance/lac', group: 'governance' },
        ]
      },
      {
        subTitle: '系统配置',
        items: [
          { label: '晋级规则', path: '/config/promotion', group: 'config' },
          { label: '防毒化规则', path: '/config/antitoxin', group: 'config' },
          { label: '数据保留策略', path: '/config/retention', group: 'config' },
        ]
      },
    ]
  },
  {
    title: '服务控制台', key: 'service',
    items: [
      { label: '站点查询', path: '/service/query', group: 'service' },
      { label: '覆盖分析', path: '/service/coverage', group: 'service' },
      { label: '统计报表', path: '/service/report', group: 'service' },
    ]
  },
]

const statusClass = computed(() => `status-${version.value.status}`)

onMounted(async () => {
  try {
    const payload = await getSystemConfig()
    version.value = payload.current_version
  } catch {
    version.value = mockVersion
  }
})
</script>

<template>
  <div class="app-layout">
    <aside class="sidebar" :class="{ collapsed }">
      <div class="sidebar-header">
        <span class="logo">rebuild5</span>
        <button class="collapse-btn" @click="collapsed = !collapsed">
          {{ collapsed ? '→' : '←' }}
        </button>
      </div>
      <nav class="sidebar-nav">
        <div v-for="section in navSections" :key="section.key" class="nav-section">
          <div class="nav-section-title">{{ section.title }}</div>
          <template v-if="section.items">
            <router-link
              v-for="item in section.items"
              :key="item.path"
              :to="item.path"
              class="nav-item"
              :class="{ active: route.path === item.path }"
            >
              {{ item.label }}
            </router-link>
          </template>
          <template v-if="section.subGroups">
            <div v-for="sg in section.subGroups" :key="sg.subTitle" class="nav-sub-group">
              <div class="nav-sub-title">{{ sg.subTitle }}</div>
              <router-link
                v-for="item in sg.items"
                :key="item.path"
                :to="item.path"
                class="nav-item"
                :class="{ active: route.path === item.path }"
              >
                {{ item.label }}
              </router-link>
            </div>
          </template>
        </div>
      </nav>
    </aside>

    <div class="main-area">
      <header class="top-bar">
        <div class="top-bar-left">
          <span class="breadcrumb text-secondary">{{ currentTitle }}</span>
        </div>
        <div class="top-bar-right">
          <span class="version-tag">
            <span class="text-muted">数据集</span>
            <span class="font-semibold">{{ version.dataset_key }}</span>
          </span>
          <span class="version-tag">
            <span class="text-muted">批次</span>
            <span class="font-mono">{{ version.run_id }}</span>
          </span>
          <span class="version-tag">
            <span class="text-muted">快照</span>
            <span class="font-mono">{{ version.snapshot_version }}</span>
          </span>
          <span class="status-badge" :class="statusClass">
            {{ PAGE_STATUS_LABELS[version.status] }}
          </span>
          <span class="text-xs text-muted">{{ version.updated_at }}</span>
        </div>
      </header>

      <main class="content">
        <router-view />
      </main>
    </div>
  </div>
</template>

<style scoped>
.app-layout {
  display: flex;
  height: 100vh;
  overflow: hidden;
}
.sidebar {
  width: var(--sidebar-width);
  background: var(--c-surface);
  border-right: 1px solid var(--c-border);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  transition: width 0.2s;
  overflow: hidden;
}
.sidebar.collapsed { width: 48px; }
.sidebar-header {
  height: var(--header-height);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--sp-md);
  border-bottom: 1px solid var(--c-border);
  flex-shrink: 0;
}
.logo {
  font-size: 15px;
  font-weight: 700;
  color: var(--c-primary);
  letter-spacing: -0.3px;
}
.collapse-btn {
  width: 24px;
  height: 24px;
  border: none;
  background: none;
  color: var(--c-text-muted);
  cursor: pointer;
  font-size: 12px;
  border-radius: var(--radius-sm);
}
.collapse-btn:hover { background: var(--c-bg); }
.sidebar-nav {
  flex: 1;
  overflow-y: auto;
  padding: var(--sp-sm) 0;
}
.nav-section { margin-bottom: var(--sp-sm); }
.nav-section-title {
  padding: var(--sp-sm) var(--sp-lg);
  font-size: 11px;
  font-weight: 600;
  color: var(--c-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.nav-sub-group {
  margin-top: 2px;
}
.nav-sub-title {
  padding: 6px var(--sp-lg) 2px 20px;
  font-size: 10.5px;
  font-weight: 600;
  color: var(--c-primary);
  opacity: 0.7;
  letter-spacing: 0.3px;
}
.nav-item {
  display: block;
  padding: 6px var(--sp-lg) 6px 28px;
  font-size: 12.5px;
  color: var(--c-text-secondary);
  text-decoration: none;
  border-left: 2px solid transparent;
  transition: all 0.1s;
}
.nav-item:hover {
  color: var(--c-text);
  background: var(--c-bg);
  text-decoration: none;
}
.nav-item.active {
  color: var(--c-primary);
  background: var(--c-primary-light);
  border-left-color: var(--c-primary);
  font-weight: 500;
}
.collapsed .nav-section-title,
.collapsed .nav-sub-title,
.collapsed .nav-item,
.collapsed .logo { display: none; }
.main-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.top-bar {
  height: var(--header-height);
  background: var(--c-surface);
  border-bottom: 1px solid var(--c-border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--sp-xl);
  flex-shrink: 0;
}
.top-bar-left { display: flex; align-items: center; gap: var(--sp-md); }
.top-bar-right { display: flex; align-items: center; gap: var(--sp-lg); }
.breadcrumb { font-size: 13px; font-weight: 500; }
.version-tag {
  display: flex;
  align-items: center;
  gap: var(--sp-xs);
  font-size: 11.5px;
}
.status-badge {
  font-size: 11px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 10px;
}
.status-published { background: #dcfce7; color: #166534; }
.status-running { background: #dbeafe; color: #1e40af; }
.status-completed { background: #e0f2fe; color: #075985; }
.status-verifying { background: #fef9c3; color: #854d0e; }
.status-reverted { background: #fee2e2; color: #991b1b; }
.content {
  flex: 1;
  overflow-y: auto;
  padding: var(--sp-xl);
}
</style>
