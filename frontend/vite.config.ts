import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Must match ALLOWED_ORIGINS in backend/app/main.py
    port: 5173,
    strictPort: true,
  },
})
