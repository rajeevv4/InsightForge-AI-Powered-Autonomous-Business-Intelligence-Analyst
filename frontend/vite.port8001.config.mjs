// Temporary local config: same as vite.config.ts but proxies /api to :8001 (port 8000 is in use).
// TEST_API_TARGET / TEST_PORT let a second dev server point at the local-DB test backend.
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
const target = process.env.TEST_API_TARGET || 'http://127.0.0.1:8001'
const port = Number(process.env.TEST_PORT || 3000)
export default defineConfig({
  plugins: [react()],
  server: { port, strictPort: true, proxy: { '/api': { target, changeOrigin: true } } }
})
