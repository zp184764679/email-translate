import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const port = parseInt(env.VITE_PORT) || 4567

  return {
    plugins: [vue()],
    base: './',
    resolve: {
      alias: {
        '@': path.resolve(__dirname, 'src')
      }
    },
    server: {
      host: '127.0.0.1',
      port: port,
      strictPort: true
      // 不需要代理，前端直连后端（后端已配置 CORS）
    },
    build: {
      outDir: 'dist',
      assetsDir: 'assets'
    }
  }
})
