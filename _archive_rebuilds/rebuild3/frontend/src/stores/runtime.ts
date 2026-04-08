import { defineStore } from 'pinia';

import { api } from '../lib/api';

export const useRuntimeStore = defineStore('runtime', {
  state: () => ({
    current: null as any,
    validation: null as any,
    principle: '',
    loading: false,
    error: '',
  }),
  actions: {
    async loadContext() {
      this.loading = true;
      this.error = '';
      try {
        const payload = await api.getCurrentRun();
        this.current = payload.current;
        this.validation = payload.validation;
        this.principle = payload.principle;
      } catch (error) {
        this.error = error instanceof Error ? error.message : '无法加载运行上下文';
      } finally {
        this.loading = false;
      }
    },
  },
});
