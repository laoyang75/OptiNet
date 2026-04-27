import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      redirect: '/global/dataset',
    },
    // 全局管理
    { path: '/global/dataset', component: () => import('../views/global/DatasetSelect.vue'), meta: { title: '数据集选择', group: 'global' } },
    { path: '/global/history', component: () => import('../views/global/RunHistory.vue'), meta: { title: '运行历史', group: 'global' } },
    // ETL 数据接入
    { path: '/etl/source', component: () => import('../views/etl/DataSource.vue'), meta: { title: '数据源注册', group: 'etl' } },
    { path: '/etl/field-audit', component: () => import('../views/etl/FieldAudit.vue'), meta: { title: '字段定义', group: 'etl' } },
    { path: '/etl/parse', component: () => import('../views/etl/Parse.vue'), meta: { title: '解析', group: 'etl' } },
    { path: '/etl/clean', component: () => import('../views/etl/Clean.vue'), meta: { title: '清洗', group: 'etl' } },
    { path: '/etl/rule-stats', component: () => import('../views/etl/RuleStats.vue'), meta: { title: 'ODS 规则命中', group: 'etl' } },
    { path: '/etl/fill', component: () => import('../views/etl/Fill.vue'), meta: { title: '补齐', group: 'etl' } },
    // 画像主链
    { path: '/profile/routing', component: () => import('../views/profile/Routing.vue'), meta: { title: '基础画像与分流', group: 'profile' } },
    // 流转评估
    { path: '/evaluation/overview', component: () => import('../views/evaluation/FlowOverview.vue'), meta: { title: '流转总览', group: 'evaluation' } },
    { path: '/evaluation/cell', component: () => import('../views/evaluation/CellEval.vue'), meta: { title: 'Cell 流转', group: 'evaluation' } },
    { path: '/evaluation/bs', component: () => import('../views/evaluation/BSEval.vue'), meta: { title: 'BS 流转', group: 'evaluation' } },
    { path: '/evaluation/lac', component: () => import('../views/evaluation/LACEval.vue'), meta: { title: 'LAC 流转', group: 'evaluation' } },
    // 治理
    { path: '/governance/fill', component: () => import('../views/governance/KnowledgeFill.vue'), meta: { title: '知识补数', group: 'governance' } },
    { path: '/governance/overview', component: () => import('../views/governance/GovernanceOverview.vue'), meta: { title: '治理总览', group: 'governance' } },
    { path: '/governance/cell', component: () => import('../views/governance/CellMaintain.vue'), meta: { title: 'Cell 维护', group: 'governance' } },
    { path: '/governance/bs', component: () => import('../views/governance/BSMaintain.vue'), meta: { title: 'BS 维护', group: 'governance' } },
    { path: '/governance/lac', component: () => import('../views/governance/LACMaintain.vue'), meta: { title: 'LAC 维护', group: 'governance' } },
    // 系统配置
    { path: '/config/promotion', component: () => import('../views/config/PromotionRules.vue'), meta: { title: '晋级规则', group: 'config' } },
    { path: '/config/antitoxin', component: () => import('../views/config/AntitoxinRules.vue'), meta: { title: '防毒化规则', group: 'config' } },
    { path: '/config/retention', component: () => import('../views/config/RetentionPolicy.vue'), meta: { title: '数据保留策略', group: 'config' } },
    // 服务控制台
    { path: '/service/query', component: () => import('../views/service/StationQuery.vue'), meta: { title: '站点查询', group: 'service' } },
    { path: '/service/coverage', component: () => import('../views/service/CoverageAnalysis.vue'), meta: { title: '覆盖分析', group: 'service' } },
    { path: '/service/report', component: () => import('../views/service/StatsReport.vue'), meta: { title: '统计报表', group: 'service' } },
  ],
})

export default router
