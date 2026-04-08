import { createRouter, createWebHistory } from 'vue-router';

import AnomalyWorkspacePage from './pages/AnomalyWorkspacePage.vue';
import BaselineProfilePage from './pages/BaselineProfilePage.vue';
import FlowOverviewPage from './pages/FlowOverviewPage.vue';
import FlowSnapshotPage from './pages/FlowSnapshotPage.vue';
import GovernancePage from './pages/GovernancePage.vue';
import InitializationPage from './pages/InitializationPage.vue';
import ObjectDetailPage from './pages/ObjectDetailPage.vue';
import ObjectsPage from './pages/ObjectsPage.vue';
import ObservationWorkspacePage from './pages/ObservationWorkspacePage.vue';
import BsProfilePage from './pages/BsProfilePage.vue';
import CellProfilePage from './pages/CellProfilePage.vue';
import LacProfilePage from './pages/LacProfilePage.vue';
import RunBatchCenterPage from './pages/RunBatchCenterPage.vue';
import ValidationComparePage from './pages/ValidationComparePage.vue';

const routes = [
  {
    path: '/',
    redirect: '/flow/overview',
  },
  {
    path: '/flow/overview',
    name: 'flow-overview',
    component: FlowOverviewPage,
    meta: {
      title: '流转总览',
      description: '以四分流、delta 和问题入口为中心的首页。',
      group: 'main',
    },
  },
  {
    path: '/flow/snapshot',
    name: 'flow-snapshot',
    component: FlowSnapshotPage,
    meta: {
      title: '流转快照',
      description: '三列时间点选择器 + 全流程数据对照表。',
      group: 'main',
    },
  },
  {
    path: '/runs',
    name: 'runs',
    component: RunBatchCenterPage,
    meta: {
      title: '运行 / 批次中心',
      description: '批次列表、结构对照与详情联动。',
      group: 'main',
    },
  },
  {
    path: '/objects',
    name: 'objects',
    component: ObjectsPage,
    meta: {
      title: '对象浏览',
      description: '统一浏览 Cell / BS / LAC 的治理状态与资格。',
      group: 'main',
    },
  },
  {
    path: '/objects/:objectType/:objectId',
    name: 'object-detail',
    component: ObjectDetailPage,
    props: true,
    meta: {
      title: '对象详情',
      description: '单对象状态、事实分布、历史和下游影响。',
      group: 'main',
    },
  },
  {
    path: '/observation',
    name: 'observation',
    component: ObservationWorkspacePage,
    meta: {
      title: '等待 / 观察工作台',
      description: '三层资格推进、堆积分析与动作建议。',
      group: 'main',
    },
  },
  {
    path: '/anomalies',
    name: 'anomalies',
    component: AnomalyWorkspacePage,
    meta: {
      title: '异常工作台',
      description: '对象级异常与记录级异常双视角。',
      group: 'main',
    },
  },
  {
    path: '/baseline',
    name: 'baseline',
    component: BaselineProfilePage,
    meta: {
      title: '基线 / 画像',
      description: '基线版本、刷新原因、差异与风险。',
      group: 'main',
    },
  },
  {
    path: '/compare',
    name: 'compare',
    component: ValidationComparePage,
    meta: {
      title: '验证 / 对照',
      description: '样本与全量双跑偏差的解释面。',
      group: 'support',
    },
  },
  {
    path: '/profiles/lac',
    name: 'profile-lac',
    component: LacProfilePage,
    meta: {
      title: 'LAC 画像',
      description: '区域级主状态、质量标签与结构指标。',
      group: 'profile',
    },
  },
  {
    path: '/profiles/bs',
    name: 'profile-bs',
    component: BsProfilePage,
    meta: {
      title: 'BS 画像',
      description: '空间锚点画像与旧分类解释层。',
      group: 'profile',
    },
  },
  {
    path: '/profiles/cell',
    name: 'profile-cell',
    component: CellProfilePage,
    meta: {
      title: 'Cell 画像',
      description: '最小治理单元的状态、质量和事实去向。',
      group: 'profile',
    },
  },
  {
    path: '/initialization',
    name: 'initialization',
    component: InitializationPage,
    meta: {
      title: '初始化数据',
      description: '冷启动 11 步流程与首版 baseline 说明。',
      group: 'support',
    },
  },
  {
    path: '/governance',
    name: 'governance',
    component: GovernancePage,
    meta: {
      title: '基础数据治理',
      description: '字段目录、表目录、实际使用与迁移状态。',
      group: 'support',
    },
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

router.afterEach((to) => {
  document.title = `${String(to.meta.title || 'rebuild3')} · rebuild3`;
});

export default router;
