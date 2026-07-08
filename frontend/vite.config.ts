import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Proxy /api to the FastAPI backend (uvicorn) so the app is same-origin in dev.
    proxy: {
      '/api': 'http://localhost:8010',
    },
  },
})
