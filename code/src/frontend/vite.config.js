import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

const backendProxy = {
  '/api': {
    target: 'http://127.0.0.1:8000',
    changeOrigin: true,
    secure: false,
    // /api/search -> /search, /api/memory -> /memory, /api/health -> /health
    rewrite: (path) => path.replace(/^\/api/, ''),
  },
};

export default defineConfig({
  plugins: [svelte()],
  // VITE_* variables live in the project-root .env next to the backend's settings.
  envDir: '..',
  server: {
    port: 5173,
    proxy: backendProxy,
  },
  preview: {
    port: 5173,
    proxy: backendProxy,
  },
});
