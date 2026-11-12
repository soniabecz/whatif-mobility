// "Add stop" tab: place a new stop on a route by clicking the map, run, and
// check the separate new-stop figures and one explorer journey with the API.

import { expect, test, type Page } from '@playwright/test'

const API = 'http://localhost:8000'

function field(page: Page, label: RegExp) {
  return page.locator('label').filter({ hasText: label })
}

test('add a stop to a route by clicking the map', async ({ page, request }) => {
  await page.goto('/')
  await expect(page.getByText('Live', { exact: true })).toBeVisible()
  await page.getByRole('radio', { name: 'Add stop' }).click()

  // One click on the middle of R1 between University and Market Square places the
  // stop there AND picks the route and that link.
  const line = page.locator('path.route-R1.link-UNI-MKT, path.route-R1.link-MKT-UNI').first()
  const box = await line.boundingBox()
  if (!box) throw new Error('R1 line not drawn')
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2)
  await expect(page.getByText(/^Placed at /)).toBeVisible()
  await expect(field(page, /^Route/).first().locator('select')).toHaveValue('R1')

  await field(page, /^Name of the new stop/).locator('input').fill('Old Market')
  await field(page, /^Minutes from/).locator('input').fill('1.5')
  await field(page, /^Minutes on to/).locator('input').fill('2')
  await page.getByRole('button', { name: 'Add to scenario' }).click()

  await expect(page.getByText(/^New stop Old Market on R1:/)).toBeVisible()
  await expect(page.locator('path.stop-N1')).toHaveCount(1) // its own marker
  await expect(page).toHaveURL(/\?s=stop:N1:Old%20Market:/)

  // The same change for the API, read back from the shareable URL.
  const [, , , lat, lon, , link, timeFrom, timeTo] = new URL(page.url()).searchParams
    .get('s')!
    .split(':')
  const [from, to] = link.split('-')
  const change = {
    type: 'add_stop', stop_id: 'N1', name: 'Old Market', lat: Number(lat), lon: Number(lon),
    route_id: 'R1', from_stop_id: from, to_stop_id: to,
    time_from_min: Number(timeFrom), time_to_min: Number(timeTo),
  }
  const { summary } = await (await request.post(`${API}/api/simulations`, { data: { changes: [change] } })).json()
  const newStops = summary.new_stops

  await page.getByRole('button', { name: 'Run simulation (1 change)' }).click()
  await page.getByRole('button', { name: 'Details' }).click()
  await expect(page.getByText('Journeys to/from new stops (not compared)')).toBeVisible()
  await expect(
    page.getByText(`${newStops.possible} of ${newStops.journeys} possible, avg ${newStops.average_time_min.toFixed(1)} min`),
  ).toBeVisible()

  // The explorer offers the new stop; its journeys are "new" (no before).
  const journey = await (await request.post(`${API}/api/journeys`, {
    data: { origin_id: 'N1', destination_id: 'AIR', changes: [change] },
  })).json()
  await page.getByRole('radio', { name: 'Journey' }).click()
  const card = page.locator('section').filter({ hasText: 'Results' }).last()
  await card.locator('label').filter({ hasText: /^From/ }).locator('select').selectOption('N1')
  await card.locator('label').filter({ hasText: /^To/ }).locator('select').selectOption('AIR')
  await expect(card.getByText('New connection')).toBeVisible()
  await expect(card.locator('h3').filter({ hasText: 'After the change' })).toContainText(
    `${journey.after.travel_time_min.toFixed(1)} min`,
  )
})
