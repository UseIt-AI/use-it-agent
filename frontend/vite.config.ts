import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import { readFileSync } from 'fs';

const pkg = JSON.parse(readFileSync(new URL('./package.json', import.meta.url), 'utf-8'));

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const viteApiUrl = (env.VITE_API_URL || '').trim();
  const useDevProxy = mode === 'development' && viteApiUrl.startsWith('/');
  const proxyTarget = (env.VITE_DEV_PROXY_TARGET || 'http://127.0.0.1:8323').trim();
  const escapedPrefix = viteApiUrl.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

  return {
  base: './',
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  server: {
    host: '127.0.0.1',
    port: 3000,
    strictPort: true,
    ...(useDevProxy
      ? {
          proxy: {
            [viteApiUrl]: {
              target: proxyTarget,
              changeOrigin: true,
              secure: false,
              rewrite: (p) =>
                p.replace(new RegExp(`^${escapedPrefix}`), '') || '/',
            },
          },
        }
      : {}),
  },
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version),
  },
  build: {
    outDir: 'dist/renderer',
    emptyOutDir: true,
    target: 'esnext',
  },
  optimizeDeps: {
    esbuildOptions: {
      target: 'esnext',
    },
  },
};
});



