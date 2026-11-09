import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// Only variables prefixed with VITE_ reach the browser bundle. Never put secrets (service-role key, DB URL) in them.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': path.resolve(import.meta.dirname, 'src') } },
  server: { port: 5173, strictPort: true },
  preview: { port: 4173, strictPort: true },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    restoreMocks: true,
  },
  build: {
    rollupOptions: {
      output: {
        // Stable vendor chunks keep the app bundle small and cacheable.
        manualChunks: {
          react: ['react', 'react-dom', 'react-router-dom'],
          supabase: ['@supabase/supabase-js'],
          data: ['@tanstack/react-query', 'axios', 'zod', 'react-hook-form'],
        },
      },
    },
  },
})
