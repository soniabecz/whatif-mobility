import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
// vitest/config is Vite's defineConfig plus the `test` section.
import { defineConfig } from 'vitest/config'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Must match ALLOWED_ORIGINS in backend/app/main.py
    port: 5173,
    strictPort: true,
  },
  test: {
    // Unit tests cover pure helpers in src/lib: no DOM needed.
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
})
