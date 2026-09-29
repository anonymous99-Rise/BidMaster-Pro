import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  root: 'renderer',
  // Electron loadFile 使用 file:// 协议，必须相对路径引用资源
  base: './',
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './renderer/src'),
    },
  },
  server: {
    port: 15168,
    host: '0.0.0.0',
    proxy: {
      '/api': {
        target: 'http://localhost:18000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: path.resolve(__dirname, './dist'),
    emptyOutDir: true,
  },
});
