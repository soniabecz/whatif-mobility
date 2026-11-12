// Smoke test of the main flow: load the map, close a stop, run, see results.
// The displayed numbers are compared with the backend's own answer for the
// same scenario, so the test checks the UI shows exactly what was computed.

import { expect, test } from '@playwright/test'

const API = 'http://localhost:8000'
const STOP_ID = 'CEN'

test('close a stop and see the simulation results', async ({ page, request }) => {
  await page.goto('/')

  // Network loaded: connection badge and all stops on the map.
  await expect(page.getByText('Live', { exact: true })).toBeVisible()
  const network = await (await request.get(`${API}/api/network`)).json()
  expect(network.stops.length).toBeGreaterThan(0)
  await expect(page.locator('path.leaflet-interactive')).not.toHaveCount(0)

  // Build the scenario with the form.
  await page.getByRole('radio', { name: 'Close stop' }).click()
  await page.getByLabel('Stop').selectOption(STOP_ID)
  await page.getByRole('button', { name: 'Add to scenario' }).click()

  // Run it.
  const run = page.getByRole('button', { name: 'Run simulation (1 change)' })
  await expect(run).toBeEnabled()
  await run.click()

  // Results appear, with the numbers the backend computes for this scenario.
  const response = await request.post(`${API}/api/simulations`, {
    data: { changes: [{ type: 'close_stop', stop_id: STOP_ID }] },
  })
  expect(response.ok()).toBe(true)
  const { summary } = await response.json()

  await expect(page.getByText(`${summary.total_journeys} journeys`)).toBeVisible()
  for (const [label, value] of [
    ['Slower', summary.slower],
    ['Faster', summary.faster],
    ['Impossible', summary.impossible],
  ] as const) {
    // Tile text is label + value (+ optional hint); the value must match exactly.
    await expect(page.getByRole('group', { name: label, exact: true })).toHaveText(
      new RegExp(`^${label}${value}(\\D|$)`),
    )
  }
  // Closing the central hub must make some journeys slower or impossible.
  expect(summary.slower + summary.impossible).toBeGreaterThan(0)
})
