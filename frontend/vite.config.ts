import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
// vitest/config is Vite's defineConfig plus the `test` section.
import { defineConfig } from 'vitest/config'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    rolldownOptions: {
      output: {
        codeSplitting: {
          // Libraries in their own file: it stays cached when only the app's code
          // changes, and no file passes Vite's 500 kB warning. (Recharts is loaded
          // with the results chart, see ResultsPanel.)
          groups: [{ name: 'vendor', test: /node_modules[\\/](react|react-dom|scheduler|leaflet|react-leaflet|@react-leaflet)[\\/]/ }],
        },
      },
    },
  },
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
