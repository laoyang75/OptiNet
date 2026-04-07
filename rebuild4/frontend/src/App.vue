<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink, RouterView } from 'vue-router'
import GlobalStatusBar from './components/GlobalStatusBar.vue'

const foundationOpen = ref(false)
</script>
<template>
  <div class="app-shell">
    <nav class="sidebar">
      <div class="sidebar-logo">rebuild4 流式治理工作台</div>

      <div class="sidebar-group">
        <div class="sidebar-group-title">主流程层</div>
        <RouterLink to="/flow-overview" class="sidebar-link">流转总览</RouterLink>
        <RouterLink to="/flow-snapshot" class="sidebar-link">流转快照</RouterLink>
        <RouterLink to="/runs" class="sidebar-link">运行/批次中心</RouterLink>
      </div>

      <div class="sidebar-group">
        <div class="sidebar-group-title">画像视角层</div>
        <RouterLink to="/objects" class="sidebar-link">对象浏览</RouterLink>
        <RouterLink to="/observation-workspace" class="sidebar-link">等待/观察工作台</RouterLink>
        <RouterLink to="/anomaly-workspace" class="sidebar-link">异常工作台</RouterLink>
        <RouterLink to="/baseline" class="sidebar-link">基线/画像</RouterLink>
        <RouterLink to="/profiles/lac" class="sidebar-link">LAC 画像</RouterLink>
        <RouterLink to="/profiles/bs" class="sidebar-link">BS 画像</RouterLink>
        <RouterLink to="/profiles/cell" class="sidebar-link">Cell 画像</RouterLink>
      </div>

      <div class="sidebar-group">
        <div class="sidebar-group-title">支撑治理层</div>
        <RouterLink to="/initialization" class="sidebar-link">初始化</RouterLink>
        <RouterLink to="/governance" class="sidebar-link">基础数据治理</RouterLink>
      </div>

      <div class="sidebar-group">
        <div class="sidebar-group-title sidebar-collapsible" @click="foundationOpen = !foundationOpen">
          <span>ETL 数据处理</span>
          <span class="collapse-arrow" :class="{ open: foundationOpen }">&#9656;</span>
        </div>
        <div v-show="foundationOpen" class="sidebar-sub">
          <RouterLink to="/etl/register" class="sidebar-link sub">1. 数据源注册</RouterLink>
          <RouterLink to="/etl/audit" class="sidebar-link sub">2. 字段审计</RouterLink>
          <RouterLink to="/etl/parse" class="sidebar-link sub">3. 解析（炸开）</RouterLink>
          <RouterLink to="/etl/clean" class="sidebar-link sub">4. 清洗</RouterLink>
          <RouterLink to="/etl/fill" class="sidebar-link sub">5. 补齐</RouterLink>
        </div>
      </div>

      <div class="sidebar-group">
        <div class="sidebar-group-title">辅助验证</div>
        <RouterLink to="/validation/compare" class="sidebar-link">验证/对照</RouterLink>
      </div>
    </nav>

    <div class="main-area">
      <header class="topbar">
        <span>rebuild4 流式治理工作台</span>
      </header>
      <GlobalStatusBar />
      <main class="page-content">
        <RouterView />
      </main>
    </div>
  </div>
</template>
