import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/jobs': 'http://127.0.0.1:8000',
      '/process': 'http://127.0.0.1:8000',
      '/tiktok/login': 'http://127.0.0.1:8000',
      '/videos': 'http://127.0.0.1:8000',
    }
  },
  build: {
    outDir: '../dist_frontend',
    emptyOutDir: true,
  }
})
