import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig, type ProxyOptions } from 'vite';

const backend = 'http://127.0.0.1:5173';
const frontend = 'http://127.0.0.1:5174';

// Only rewrite our own development origin; foreign origins must reach the
// backend unchanged so its local-origin check still rejects them.
const apiProxy: ProxyOptions = {
  target: backend,
  changeOrigin: true,
  configure(proxy) {
    proxy.on('proxyReq', (request, incoming) => {
      if (incoming.headers.origin === frontend) request.setHeader('origin', backend);
    });
    proxy.on('proxyReqWs', (request, incoming) => {
      if (incoming.headers.origin === frontend) request.setHeader('origin', backend);
    });
  },
};

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: '127.0.0.1',
    port: 5174,
    strictPort: true,
    proxy: {
      '/api': apiProxy,
      '/ws': { ...apiProxy, ws: true },
    },
  },
});
