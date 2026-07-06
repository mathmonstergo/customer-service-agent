import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'

const ADMIN_API_TARGET = process.env.ADMIN_API_TARGET || 'http://127.0.0.1:8080'

// 清理构建产物的行尾空白，避免新增 split chunk 时触发 Git whitespace 检查。
function stripGeneratedChunkTrailingWhitespace(): Plugin {
  return {
    name: 'strip-generated-chunk-trailing-whitespace',
    generateBundle(_, bundle) {
      // Rolldown 生成部分 vendor chunk 时会保留模板字符串空行空格，这里只清理最终 JS 文本。
      for (const chunk of Object.values(bundle)) {
        if (chunk.type === 'chunk') {
          chunk.code = chunk.code.replace(/[ \t]+$/gm, '')
        }
      }
    },
  }
}

export default defineConfig({
  base: '/static/dist/',
  plugins: [react(), tailwindcss(), stripGeneratedChunkTrailingWhitespace()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    outDir: '../cyclops/static/dist',
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': { target: ADMIN_API_TARGET, changeOrigin: true },
    },
  },
})
