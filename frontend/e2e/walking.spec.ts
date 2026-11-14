// Walking from a closed stop: the journey explorer shows the walk and the
// backend's own time for it.

import { expect, test } from '@playwright/test'

const API = 'http://localhost:8000'
const CHANGES = [{ type: 'close_stop', stop_id: 'CEN' }]

test('a journey from a closed stop walks to a nearby stop', async ({ page, request }) => {
  const response = await request.post(`${API}/api/journeys`, {
    data: { origin_id: 'CEN', destination_id: 'AIR', changes: CHANGES },
  })
  const { after } = await response.json()
  const [walkStart] = after.walks
  expect(walkStart?.before_leg).toBe(0) // needs walking on (the default)

  await page.goto('/?s=close:CEN')
  await page.getByRole('button', { name: 'Run simulation (1 change)' }).click()
  await page.getByRole('radio', { name: 'Journey' }).click()
  const card = page.locator('section').filter({ hasText: 'Results' }).last()
  await card.locator('label').filter({ hasText: /^From/ }).locator('select').selectOption('CEN')
  await card.locator('label').filter({ hasText: /^To/ }).locator('select').selectOption('AIR')

  await expect(card.getByText(`Walk about ${Math.round(walkStart.distance_m)} m from Central Station`)).toBeVisible()
  await expect(card.getByText(`${after.walk_min.toFixed(1)} min walking +`)).toBeVisible()
  await expect(
    card.locator('h3').filter({ hasText: 'After the change' }),
  ).toContainText(`${after.travel_time_min.toFixed(1)} min`)
})
