import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', redirect: '/flow-overview' },
  // Main flow
  { path: '/flow-overview', component: () => import('./pages/FlowOverviewPage.vue'), meta: { group: 'main', title: '流转总览' } },
  { path: '/flow-snapshot', component: () => import('./pages/FlowSnapshotPage.vue'), meta: { group: 'main', title: '流转快照' } },
  { path: '/runs', component: () => import('./pages/RunBatchCenterPage.vue'), meta: { group: 'main', title: '运行/批次中心' } },
  // Profile view
  { path: '/objects', component: () => import('./pages/ObjectsPage.vue'), meta: { group: 'profile', title: '对象浏览' } },
  { path: '/objects/:objectType/:objectId', component: () => import('./pages/ObjectDetailPage.vue'), meta: { group: 'profile', title: '对象详情' }, props: true },
  { path: '/observation-workspace', component: () => import('./pages/ObservationWorkspacePage.vue'), meta: { group: 'profile', title: '等待/观察工作台' } },
  { path: '/anomaly-workspace', component: () => import('./pages/AnomalyWorkspacePage.vue'), meta: { group: 'profile', title: '异常工作台' } },
  { path: '/baseline', component: () => import('./pages/BaselineProfilePage.vue'), meta: { group: 'profile', title: '基线/画像' } },
  { path: '/profiles/lac', component: () => import('./pages/LacProfilePage.vue'), meta: { group: 'profile', title: 'LAC 画像' } },
  { path: '/profiles/bs', component: () => import('./pages/BsProfilePage.vue'), meta: { group: 'profile', title: 'BS 画像' } },
  { path: '/profiles/cell', component: () => import('./pages/CellProfilePage.vue'), meta: { group: 'profile', title: 'Cell 画像' } },
  // Support
  { path: '/governance', component: () => import('./pages/GovernancePage.vue'), meta: { group: 'support', title: '基础数据治理' } },
  // ETL 数据处理
  { path: '/etl/register', component: () => import('./pages/EtlRegisterPage.vue'), meta: { group: 'etl', title: '数据源注册' } },
  { path: '/etl/audit', component: () => import('./pages/EtlAuditPage.vue'), meta: { group: 'etl', title: '字段审计' } },
  { path: '/etl/parse', component: () => import('./pages/EtlParsePage.vue'), meta: { group: 'etl', title: '解析（炸开）' } },
  { path: '/etl/clean', component: () => import('./pages/EtlCleanPage.vue'), meta: { group: 'etl', title: '清洗' } },
  { path: '/etl/fill', component: () => import('./pages/EtlFillPage.vue'), meta: { group: 'etl', title: '补齐' } },
  // Auxiliary
  { path: '/validation/compare', component: () => import('./pages/ValidationComparePage.vue'), meta: { group: 'aux', title: '验证/对照' } },
]

const router = createRouter({ history: createWebHistory(), routes })

router.afterEach((to) => {
  document.title = `${(to.meta as any).title || 'rebuild4'} - rebuild4 流式治理工作台`
})

export default router
