// "Frequency" tab: make a route run more often and see faster journeys.

import { expect, test } from '@playwright/test'

const API = 'http://localhost:8000'

test('change how often a route runs', async ({ page, request }) => {
  await page.goto('/')
  await expect(page.getByText('Live', { exact: true })).toBeVisible()

  await page.getByRole('radio', { name: 'Frequency' }).click()
  await page.locator('label').filter({ hasText: /^Route/ }).locator('select').selectOption('R3')
  const headway = page.locator('label').filter({ hasText: /^A bus every/ }).locator('input')
  await expect(headway).toHaveValue('15') // current headway filled in
  await headway.fill('7.5')
  await page.getByRole('button', { name: 'Add to scenario' }).click()

  // Listed, shareable and shown in the legend.
  await expect(page.getByText('R3: a bus every 7.5 min')).toBeVisible()
  await expect(page).toHaveURL(/\?s=freq:R3:7\.5$/)

  await page.getByRole('button', { name: 'Run simulation (1 change)' }).click()

  // The KPI tiles show the backend's own result for the same scenario.
  const response = await request.post(`${API}/api/simulations`, {
    data: { changes: [{ type: 'change_frequency', route_id: 'R3', headway_min: 7.5 }] },
  })
  const { summary } = await response.json()
  expect(summary.faster).toBeGreaterThan(0) // needs waiting on (the default)
  await expect(page.getByRole('group', { name: 'Faster', exact: true })).toHaveText(
    new RegExp(`^Faster${summary.faster}(\\D|$)`),
  )
  await expect(page.getByRole('group', { name: 'Slower', exact: true })).toHaveText(/^Slower0(\D|$)/)
})
