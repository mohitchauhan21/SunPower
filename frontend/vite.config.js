import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The SunPower back end (FastAPI) runs on :8001 and the AI service on :8000.
// The React app proxies both (in `vite` and `vite preview`), so the browser sees
// one origin: the session cookie works and neither server needs CORS.
const BACKEND = process.env.SUNPOWER_BACKEND || 'http://localhost:8001';
const AI = process.env.SUNPOWER_AI || 'http://localhost:8000';

const proxy = {
  '/api': { target: BACKEND, changeOrigin: true },
  '/print': { target: BACKEND, changeOrigin: true },
  '/ai': { target: AI, changeOrigin: true, rewrite: (p) => p.replace(/^\/ai/, '') }
};

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy },
  preview: { port: 4173, proxy }
});
