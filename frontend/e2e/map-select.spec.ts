// Clicking stops and lines on the map fills in the scenario form.

import { expect, test, type Locator, type Page } from '@playwright/test'

const API = 'http://localhost:8000'

interface Stop {
  id: string
  name: string
}
interface Connection {
  route_id: string
  from_stop_id: string
  to_stop_id: string
}

/**
 * Click the middle of an SVG line with the mouse. Locator.click() refuses
 * horizontal or vertical lines: their geometric bounding box is 0 px wide or
 * high, so Playwright treats them as invisible (the stroke is not counted).
 */
async function clickLineMiddle(page: Page, line: Locator) {
  await line.waitFor({ state: 'attached' })
  const box = await line.boundingBox()
  if (!box) throw new Error('line has no bounding box')
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2)
}

/**
 * The <select> inside the form field labelled `name`. (getByLabel matches
 * substrings, and "To" is part of "Stop"; the accessible name also contains
 * the selected option, so an exact match does not work either.)
 */
function field(page: Page, name: string): Locator {
  return page.locator('label').filter({ hasText: new RegExp(`^${name}`) }).locator('select')
}

test('clicking the map fills in the scenario form', async ({ page, request }) => {
  const network = await (await request.get(`${API}/api/network`)).json()
  const stops = new Map<string, Stop>(network.stops.map((s: Stop) => [s.id, s]))
  const connections: Connection[] = network.connections

  await page.goto('/')
  await expect(page.getByText('Live', { exact: true })).toBeVisible()

  // 1. "Close stop": clicking a stop selects it.
  await page.locator('path.stop-UNI').click()
  await expect(field(page, 'Stop')).toHaveValue('UNI')

  // 2. Clicking a line switches to "Remove link" and selects that link.
  // The map draws each route's street once, in the direction it first appears.
  const link = connections[0]
  await clickLineMiddle(
    page,
    page.locator(`path.route-${link.route_id}.link-${link.from_stop_id}-${link.to_stop_id}`),
  )
  await expect(page.getByRole('radio', { name: 'Remove link' })).toHaveAttribute('aria-checked', 'true')
  await expect(field(page, 'From')).toHaveValue(link.from_stop_id)
  await expect(field(page, 'To')).toHaveValue(link.to_stop_id)

  // 3. Two neighbouring stops: the first click sets From, the second sets To.
  const other = connections.find(
    (c) => c.from_stop_id !== link.from_stop_id && c.to_stop_id !== link.to_stop_id,
  )!
  await page.locator(`path.stop-${other.from_stop_id}`).click()
  await expect(field(page, 'From')).toHaveValue(other.from_stop_id)
  await expect(
    page.getByText(`Now click a stop next to ${stops.get(other.from_stop_id)!.name} on the map.`),
  ).toBeVisible()
  await page.locator(`path.stop-${other.to_stop_id}`).click()
  await expect(field(page, 'To')).toHaveValue(other.to_stop_id)

  // The selection can be added like any other change.
  await page.getByRole('button', { name: 'Add to scenario' }).click()
  await expect(page.getByRole('button', { name: 'Run simulation (1 change)' })).toBeEnabled()
})
