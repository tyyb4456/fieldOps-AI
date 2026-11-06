import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'
import tailwindcss from '@tailwindcss/vite'
import { resolveApiBaseUrl } from './src/lib/api-url.ts'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  resolveApiBaseUrl(env.VITE_API_BASE_URL, {
    isProduction: mode === 'production',
  })

  return {
    plugins: [react(), tailwindcss()],
  }
})
