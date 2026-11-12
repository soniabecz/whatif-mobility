// End-to-end test: real backend + real frontend in a real browser.
// Run with `npm run test:e2e` (first time: `npx playwright install chromium`).
// The backend needs the seeded sample network (`python -m app.seed`).

import { defineConfig, devices } from '@playwright/test'

const isCI = Boolean(process.env.CI)

// Locally the backend runs from its virtual environment; CI installs the
// packages globally and sets E2E_PYTHON=python.
const python = process.env.E2E_PYTHON ?? '.venv/bin/python'

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  forbidOnly: isCI,
  retries: isCI ? 1 : 0,
  reporter: isCI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    // Must be the Vite dev server origin allowed by the backend's CORS list.
    baseURL: 'http://localhost:5173',
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  // Both servers are started for the test, or reused when already running locally.
  webServer: [
    {
      command: `${python} -m uvicorn app.main:app --port 8000`,
      cwd: '../backend',
      url: 'http://localhost:8000/api/health',
      reuseExistingServer: !isCI,
      timeout: 60_000,
    },
    {
      command: 'npm run dev',
      url: 'http://localhost:5173',
      reuseExistingServer: !isCI,
      timeout: 60_000,
    },
  ],
})
