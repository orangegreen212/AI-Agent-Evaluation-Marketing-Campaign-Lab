import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath, URL } from 'node:url';

// Local development: the FastAPI backend binds to 127.0.0.1:8000 (loopback only, no CORS).
// Requests to /v1 from the browser are forwarded server-side by Vite, so the browser
// only ever talks to its own origin. Start the backend first: `python -m lab.api --port 8000`.
const BACKEND_TARGET = 'http://127.0.0.1:8000';
const proxy = {
  '/v1': {
    target: BACKEND_TARGET,
    changeOrigin: false,
  },
};

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: { proxy },
  preview: { proxy },
  optimizeDeps: {
    exclude: ['lucide-react'],
  },
});
