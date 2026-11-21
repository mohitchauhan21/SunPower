import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The SunPower engine (Odoo) runs on :8069 and the AI service on :8000. The React app
// proxies both (in `vite` and `vite preview`), so the browser sees one origin: the staff
// session cookie works and the AI service needs no extra CORS entry.
const ENGINE = process.env.SUNPOWER_ENGINE || 'http://localhost:8069';
const AI = process.env.SUNPOWER_AI || 'http://localhost:8000';

const proxy = {
  '/api': { target: ENGINE, changeOrigin: true },
  '/web': { target: ENGINE, changeOrigin: true },
  '/ai': { target: AI, changeOrigin: true, rewrite: (p) => p.replace(/^\/ai/, '') }
};

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy },
  preview: { port: 4173, proxy }
});
