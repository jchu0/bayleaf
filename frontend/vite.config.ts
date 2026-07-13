import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Pin the dev port. The app assumes :5173 in a few real places — the API's CORS
    // allowlist (api/main.py) and the Admin /metrics origin swap (Admin.tsx) — and the
    // README/run-of-show tell operators to open :5173. Vite's default port is 5173 but is
    // NOT strict: if 5173 is busy it silently drifts to 5174, which would break those
    // assumptions. strictPort makes it deterministic (fail loudly instead of drift).
    port: 5173,
    strictPort: true,
    // Proxy /api to the FastAPI backend (uvicorn) so the app is same-origin in dev.
    proxy: {
      '/api': 'http://localhost:8010',
    },
  },
})
