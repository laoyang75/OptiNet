import { createRouter, createWebHistory } from 'vue-router';

import CellDetailPage from './pages/CellDetailPage.vue';
import CellObjectsPage from './pages/CellObjectsPage.vue';
import CellProfilePage from './pages/CellProfilePage.vue';

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      redirect: '/cells',
    },
    {
      path: '/cells',
      name: 'cell-objects',
      component: CellObjectsPage,
      meta: {
        title: 'Cell 对象浏览',
      },
    },
    {
      path: '/cells/:objectId',
      name: 'cell-detail',
      component: CellDetailPage,
      props: true,
      meta: {
        title: 'Cell 对象详情',
      },
    },
    {
      path: '/cells/:objectId/profile',
      name: 'cell-profile',
      component: CellProfilePage,
      props: true,
      meta: {
        title: 'Cell 画像',
      },
    },
  ],
});

router.afterEach((to) => {
  const title = typeof to.meta.title === 'string' ? to.meta.title : 'Cell Workbench';
  document.title = `${title} · rebuild3`;
});

export default router;
