<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import { mockVersion } from '../mock/data'
import { PAGE_STATUS_LABELS } from '../types'

const route = useRoute()
const collapsed = ref(false)
const currentTitle = computed(() => (route.meta?.title as string) || '')

interface NavItem { label: string; path: string; group: string }
interface NavSection { title: string; key: string; items: NavItem[] }

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
    items: [
      { label: '数据源注册', path: '/etl/source', group: 'etl' },
      { label: '字段审计', path: '/etl/field-audit', group: 'etl' },
      { label: '解析', path: '/etl/parse', group: 'etl' },
      { label: '清洗', path: '/etl/clean', group: 'etl' },
      { label: '补齐', path: '/etl/fill', group: 'etl' },
      { label: '基础画像与分流', path: '/profile/routing', group: 'profile' },
      { label: '流转总览', path: '/evaluation/overview', group: 'evaluation' },
      { label: '流转快照', path: '/evaluation/snapshot', group: 'evaluation' },
      { label: '观察工作台', path: '/evaluation/watchlist', group: 'evaluation' },
      { label: 'Cell 评估', path: '/evaluation/cell', group: 'evaluation' },
      { label: 'BS 评估', path: '/evaluation/bs', group: 'evaluation' },
      { label: 'LAC 评估', path: '/evaluation/lac', group: 'evaluation' },
      { label: '知识补数', path: '/governance/fill', group: 'governance' },
      { label: 'Cell 维护', path: '/governance/cell', group: 'governance' },
      { label: 'BS 维护', path: '/governance/bs', group: 'governance' },
      { label: 'LAC 维护', path: '/governance/lac', group: 'governance' },
      { label: '晋级规则', path: '/config/promotion', group: 'config' },
      { label: '防毒化规则', path: '/config/antitoxin', group: 'config' },
      { label: '数据保留策略', path: '/config/retention', group: 'config' },
    ]
  },
  {
    title: '服务控制台', key: 'service',
    items: [
      { label: '基站查询', path: '/service/query', group: 'service' },
      { label: '覆盖分析', path: '/service/coverage', group: 'service' },
      { label: '统计报表', path: '/service/report', group: 'service' },
    ]
  },
]

const statusClass = computed(() => `status-${mockVersion.status}`)
</script>

<template>
  <div class="app-layout">
    <!-- 侧边栏 -->
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
          <router-link
            v-for="item in section.items"
            :key="item.path"
            :to="item.path"
            class="nav-item"
            :class="{ active: route.path === item.path }"
          >
            {{ item.label }}
          </router-link>
        </div>
      </nav>
    </aside>

    <!-- 主区域 -->
    <div class="main-area">
      <!-- 顶部版本条 -->
      <header class="top-bar">
        <div class="top-bar-left">
          <span class="breadcrumb text-secondary">{{ currentTitle }}</span>
        </div>
        <div class="top-bar-right">
          <span class="version-tag">
            <span class="text-muted">数据集</span>
            <span class="font-semibold">{{ mockVersion.dataset_key }}</span>
          </span>
          <span class="version-tag">
            <span class="text-muted">批次</span>
            <span class="font-mono">{{ mockVersion.run_id }}</span>
          </span>
          <span class="version-tag">
            <span class="text-muted">快照</span>
            <span class="font-mono">{{ mockVersion.snapshot_version }}</span>
          </span>
          <span class="status-badge" :class="statusClass">
            {{ PAGE_STATUS_LABELS[mockVersion.status] }}
          </span>
          <span class="text-xs text-muted">{{ mockVersion.updated_at }}</span>
        </div>
      </header>

      <!-- 内容区 -->
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

/* 侧边栏 */
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
.collapsed .nav-item,
.collapsed .logo { display: none; }

/* 主区域 */
.main-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* 顶部版本条 */
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

/* 内容区 */
.content {
  flex: 1;
  overflow-y: auto;
  padding: var(--sp-xl);
}
</style>
