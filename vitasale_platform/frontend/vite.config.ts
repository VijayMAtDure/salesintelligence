import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Proxies /api/* to the Django dev server — both run on the same box (the GPU server),
// so this sidesteps CORS entirely rather than needing it configured correctly on both
// sides. See DJANGO_PLATFORM_ARCHITECTURE.md §5.4.
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8010',
        changeOrigin: true,
      },
    },
  },
})
