import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'

const ADMIN_API_TARGET = process.env.ADMIN_API_TARGET || 'http://127.0.0.1:8080'

export default defineConfig({
  base: '/static/dist/',
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    outDir: '../customer_service_agent/static/dist',
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': { target: ADMIN_API_TARGET, changeOrigin: true },
    },
  },
})
