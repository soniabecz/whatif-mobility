// "Add link" tab: extend a route with a new link and see faster journeys.

import { expect, test, type Page } from '@playwright/test'

const API = 'http://localhost:8000'

function field(page: Page, label: RegExp) {
  return page.locator('label').filter({ hasText: label })
}

test('add a link to a route with the form', async ({ page, request }) => {
  await page.goto('/')
  await expect(page.getByText('Live', { exact: true })).toBeVisible()
  await page.getByRole('radio', { name: 'Add link' }).click()

  // From and To by clicking two stops on the map (not neighbours: fine for a new link).
  await page.locator('path.stop-EST').click()
  await page.locator('path.stop-TEC').click()
  await field(page, /^Route that gets/).locator('select').selectOption('R2')
  await expect(field(page, /^From/).locator('select')).toHaveValue('EST')
  await expect(field(page, /^To/).locator('select')).toHaveValue('TEC')

  // No time is pre-filled: the button stays disabled until one is entered.
  const time = field(page, /^Travel time/).locator('input')
  await expect(time).toHaveValue('')
  await expect(page.getByRole('button', { name: 'Add to scenario' })).toBeDisabled()
  await time.fill('5')
  await page.getByRole('button', { name: 'Add to scenario' }).click()

  await expect(page.getByText('Add R2: East Gate ↔ Tech Park, 5 min')).toBeVisible()
  await expect(page).toHaveURL(/\?s=add:R2:EST-TEC:5$/)
  await expect(page.locator('path.added-EST-TEC')).toHaveCount(1) // dashed line on the map

  await page.getByRole('button', { name: 'Run simulation (1 change)' }).click()
  const response = await request.post(`${API}/api/simulations`, {
    data: {
      changes: [
        { type: 'add_connection', route_id: 'R2', from_stop_id: 'EST', to_stop_id: 'TEC', travel_time_min: 5 },
      ],
    },
  })
  const { summary } = await response.json()
  expect(summary.faster).toBeGreaterThan(0)
  const value = (label: string) =>
    page.getByRole('group', { name: label, exact: true }).locator('p').nth(1)
  await expect(value('Faster')).toHaveText(String(summary.faster))
  await expect(value('Slower')).toHaveText('0')
})

test('the form explains a link the route cannot get', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByText('Live', { exact: true })).toBeVisible()
  await page.getByRole('radio', { name: 'Add link' }).click()
  await field(page, /^Route that gets/).locator('select').selectOption('R2')
  await field(page, /^From/).locator('select').selectOption('MUS')
  await field(page, /^To/).locator('select').selectOption('TEC')
  await field(page, /^Travel time/).locator('input').fill('5')
  await expect(page.getByText('Not possible: route R2 stops at neither MUS nor TEC.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Add to scenario' })).toBeDisabled()
})
