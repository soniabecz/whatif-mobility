// End-to-end test: real backend + real frontend in a real browser.
// Run with `npm run test:e2e` (first time: `npx playwright install chromium`).
// The tests run on the invented sample city (test data; the app itself runs on
// Gdańsk): the backend command seeds it into its own test database first.

import { defineConfig, devices } from '@playwright/test'

const isCI = Boolean(process.env.CI)

// Locally the backend runs from its virtual environment; CI installs the
// packages globally and sets E2E_PYTHON=python.
const python = process.env.E2E_PYTHON ?? '.venv/bin/python'

export default defineConfig({
  testDir: './e2e',
  // Runs after the servers are up: refuses a reused backend that serves another network.
  globalSetup: './e2e/global-setup.ts',
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
      command: `${python} -m app.seed && ${python} -m uvicorn app.main:app --port 8000`,
      cwd: '../backend',
      // A separate test database, freshly seeded on every run (never the app's gdansk.db).
      env: { WHATIF_DATABASE: 'e2e-sample.db' },
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
