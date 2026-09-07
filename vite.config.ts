import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import {defineConfig} from 'vite';

export default defineConfig(() => {
  return {
    base: './',
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, '.'),
      },
    },
    server: {
      watch: {
        ignored: [
          '**/data/**',
          '**/*.db*',
          '**/*.sqlite*',
          '**/.venv/**',
          '**/venv/**',
          '**/*.wav',
          '**/*.mp3',
          '**/*.log',
        ],
      },
    },
  };
});
