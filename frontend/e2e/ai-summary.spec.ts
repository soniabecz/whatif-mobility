// "Summarise with AI" (Day 12). CI has no AI key, so the summary endpoint is
// answered here; the placeholder check and the filling in of numbers are covered
// by backend/tests/test_ai_summary.py. This checks the UI: the request, the
// summary card, "withheld", and that a new result drops the old summary.

import { expect, test, type Page } from '@playwright/test'

async function run(page: Page, changes: number) {
  await page.getByRole('button', { name: `Run simulation (${changes} change${changes === 1 ? '' : 's'})` }).click()
  await expect(page.getByRole('button', { name: 'Summarise with AI' })).toBeVisible()
}

test('the AI summary is requested on demand and belongs to one result', async ({ page }) => {
  const sent: unknown[] = []
  await page.route('**/api/ai/summary', async (route) => {
    sent.push(route.request().postDataJSON())
    await route.fulfill({
      json: { status: 'ok', summary: 'Closing Central Station makes 120 journeys slower.', message: '' },
    })
  })
  await page.goto('/?s=close:CEN')
  await run(page, 1)
  expect(sent).toEqual([]) // nothing is sent until asked

  await page.getByRole('button', { name: 'Summarise with AI' }).click()
  expect(sent).toEqual([{ changes: [{ type: 'close_stop', stop_id: 'CEN' }] }])
  const card = page.getByRole('figure')
  await expect(card).toContainText('Closing Central Station makes 120 journeys slower.')
  await expect(card).toContainText('Every number was inserted from them')

  // A new result drops the summary of the old one.
  await page.getByRole('button', { name: 'Remove change 1' }).click()
  await page.getByRole('radio', { name: 'Close stop' }).click()
  await page.locator('path.stop-AIR').click()
  await page.getByRole('button', { name: 'Add to scenario' }).click()
  await run(page, 1)
  await expect(page.getByRole('figure')).toHaveCount(0)
})

test('a withheld summary explains why and can be tried again', async ({ page }) => {
  let calls = 0
  await page.route('**/api/ai/summary', (route) => {
    calls += 1
    return route.fulfill({
      json: calls === 1
        ? { status: 'withheld', summary: null,
            message: 'The AI summary was withheld because it did not stick to the computed figures.' }
        : { status: 'ok', summary: 'Most journeys are unchanged.', message: '' },
    })
  })
  await page.goto('/?s=close:CEN')
  await run(page, 1)
  await page.getByRole('button', { name: 'Summarise with AI' }).click()
  await expect(page.getByRole('status').filter({ hasText: 'withheld' })).toBeVisible()

  await page.getByRole('button', { name: 'Try again' }).click()
  await expect(page.getByRole('figure')).toContainText('Most journeys are unchanged.')
})
