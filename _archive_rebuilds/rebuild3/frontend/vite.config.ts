import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';

const backendHost = process.env.REBUILD3_BACKEND_HOST ?? '127.0.0.1';
const backendPort = process.env.REBUILD3_BACKEND_PORT ?? '47121';

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': `http://${backendHost}:${backendPort}`,
    },
  },
});
