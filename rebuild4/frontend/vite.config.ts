import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 47132,
    host: '0.0.0.0',
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:47131',
        changeOrigin: true,
      },
    },
  },
})
