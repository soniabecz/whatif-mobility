// "Add route" tab: draw a new line by clicking stops in order, give the times and
// headway, see it on the map and in the legend, run, and use it in a later change.

import { expect, test, type Page } from '@playwright/test'

const API = 'http://localhost:8000'

function field(page: Page, label: RegExp) {
  return page.locator('label').filter({ hasText: label })
}

const CROSS_TOWN = {
  type: 'add_route', route_id: 'R5', name: 'Cross Town', color: '#7c3aed', headway_min: 12,
  stop_ids: ['OLD', 'MKT', 'RIV'], travel_times_min: [3, 4], is_loop: false, both_directions: true,
}

test('add a route by clicking stops on the map', async ({ page, request }) => {
  await page.goto('/')
  await expect(page.getByText('Live', { exact: true })).toBeVisible()
  await page.getByRole('radio', { name: 'Add route' }).click()

  // Stops in the order the bus calls; a dashed preview follows the clicks.
  for (const stop of ['OLD', 'MKT', 'RIV']) await page.locator(`path.stop-${stop}`).click()
  const stops = page.getByRole('list', { name: 'Stops of the new route' })
  await expect(stops.getByRole('listitem')).toHaveText([/Old Town/, /Market Square/, /Riverside/])
  await expect(page.locator('path.new-route-preview')).toHaveCount(1)

  // Nothing is guessed: name, headway and every time are required.
  const add = page.getByRole('button', { name: 'Add to scenario' })
  await expect(add).toBeDisabled()
  await field(page, /^Name of the new route/).locator('input').fill('Cross Town')
  await field(page, /^A bus every/).locator('input').fill('12')
  await page.getByLabel('Minutes from Old Town to Market Square').fill('3')
  await expect(page.getByText('Market Square → Riverside: Travel time must be a number greater than 0.')).toBeVisible()
  await page.getByLabel('Minutes from Market Square to Riverside').fill('4')
  await expect(page.getByRole('radio', { name: 'Violet' })).toHaveAttribute('aria-checked', 'true')
  await add.click()

  await expect(
    page.getByText('New route R5 Cross Town, every 12 min: Old Town ↔ Market Square ↔ Riverside (3 + 4 min)'),
  ).toBeVisible()
  await expect(page).toHaveURL(/\?s=route:R5:Cross%20Town:7c3aed:12:OLD-MKT-RIV:3-4$/)
  await expect(page.locator('path.added-route.route-R5')).toHaveCount(2) // dashed, one per stretch
  await expect(page.getByRole('listitem').filter({ hasText: /^R5 Cross Townnew/ })).toBeVisible() // legend
  // The form starts the next route empty; violet is taken now.
  await expect(stops).toHaveCount(0)
  await expect(page.getByRole('radio', { name: 'Violet (used by another route)' })).toBeDisabled()

  // A later change can pick the new route by clicking its line.
  await page.getByRole('radio', { name: 'Frequency' }).click()
  await page.locator('path.added-route.route-R5').first().click()
  await expect(field(page, /^Route/).locator('select')).toHaveValue('R5')
  await expect(field(page, /^A bus every/).locator('input')).toHaveValue('12')

  // The results match the API's.
  const response = await request.post(`${API}/api/simulations`, { data: { changes: [CROSS_TOWN] } })
  const { summary } = await response.json()
  expect(summary.faster).toBeGreaterThan(0)
  await page.getByRole('button', { name: 'Run simulation (1 change)' }).click()
  const value = (label: string) => page.getByRole('group', { name: label, exact: true }).locator('p').nth(1)
  await expect(value('Faster')).toHaveText(String(summary.faster))
  await expect(value('Slower')).toHaveText('0')
})

test('clicking the first stop again makes a loop that needs a time back', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByText('Live', { exact: true })).toBeVisible()
  await page.getByRole('radio', { name: 'Add route' }).click()
  for (const stop of ['OLD', 'MKT', 'RIV', 'OLD']) await page.locator(`path.stop-${stop}`).click()

  await expect(page.getByRole('switch', { name: 'Loop (back to the first stop)' })).toBeChecked()
  await field(page, /^Name of the new route/).locator('input').fill('Little Ring')
  await field(page, /^A bus every/).locator('input').fill('15')
  await page.getByLabel('Minutes from Old Town to Market Square').fill('3')
  await page.getByLabel('Minutes from Market Square to Riverside').fill('4')
  await expect(page.getByText('Riverside → Old Town: Travel time must be a number greater than 0.')).toBeVisible()
  await page.getByLabel('Minutes from Riverside back to Old Town').fill('6')
  await field(page, /^Both directions/).click() // one way, like many rings
  await page.getByRole('button', { name: 'Add to scenario' }).click()

  await expect(page.getByText(/Old Town → Market Square → Riverside → Old Town \(loop, 3 \+ 4 \+ 6 min\)/)).toBeVisible()
  await expect(page).toHaveURL(/:OLD-MKT-RIV:3-4-6:loop:oneway$/)
  await expect(page.locator('path.added-route.route-R5')).toHaveCount(3)
})
