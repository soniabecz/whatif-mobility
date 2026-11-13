// The AI edits the current change list (Day 12). CI has no AI key, so the AI
// endpoint is answered here; the backend's handling of the AI's operations is
// covered by backend/tests/test_ai_change_list.py. This checks the UI wiring:
// the list is sent, the new list replaces it, Undo, and the stale-answer guard.

import { expect, test, type Page, type Route } from '@playwright/test'

const CLOSE_CEN = { type: 'close_stop', stop_id: 'CEN' }
const CLOSE_AIR = { type: 'close_stop', stop_id: 'AIR' }

async function ask(page: Page, text: string) {
  await page.getByLabel('Describe a change in plain language').fill(text)
  await page.getByRole('button', { name: 'Interpret' }).click()
}

test('the AI replaces the list with its edit, and Undo restores it', async ({ page }) => {
  const sent: unknown[] = []
  await page.route('**/api/ai/interpret', async (route: Route) => {
    sent.push(route.request().postDataJSON())
    await route.fulfill({
      json: {
        status: 'ok', changes: [CLOSE_AIR], removed: [1], replaced: [], added: 1,
        message: 'Closed the Airport instead of Central Station.',
      },
    })
  })
  await page.goto('/?s=close:CEN')
  await expect(page.getByText('Close Central Station')).toBeVisible()

  await ask(page, 'the airport instead')
  expect(sent).toEqual([{ text: 'the airport instead', current_changes: [CLOSE_CEN] }])
  await expect(page.getByRole('status').filter({ hasText: 'Removed 1 · added 1.' })).toContainText(
    'Closed the Airport instead of Central Station.',
  )
  await expect(page.getByText('Close Airport')).toBeVisible()
  await expect(page.getByText('Close Central Station')).toHaveCount(0)
  await expect(page).toHaveURL(/\?s=close:AIR$/)

  await page.getByRole('button', { name: 'Undo' }).click()
  await expect(page.getByText('Close Central Station')).toBeVisible()
  await expect(page.getByText('Close Airport')).toHaveCount(0)
  await expect(page.getByText('Undone: the list is back as it was.')).toBeVisible()
  await expect(page).toHaveURL(/\?s=close:CEN$/)
})

test('Undo disappears once the list is edited by hand', async ({ page }) => {
  await page.route('**/api/ai/interpret', (route) =>
    route.fulfill({
      json: { status: 'ok', changes: [CLOSE_CEN, CLOSE_AIR], removed: [], replaced: [], added: 1, message: 'Done.' },
    }),
  )
  await page.goto('/?s=close:CEN')
  await ask(page, 'and also the airport')
  await expect(page.getByRole('button', { name: 'Undo' })).toBeVisible()
  await page.getByRole('button', { name: 'Remove change 1' }).click()
  await expect(page.getByRole('button', { name: 'Undo' })).toHaveCount(0)
})

test('an answer for a list that changed meanwhile is not applied', async ({ page }) => {
  let release: () => void = () => {}
  const answered = new Promise<void>((resolve) => (release = resolve))
  await page.route('**/api/ai/interpret', async (route) => {
    await answered // hold the answer until the list has been edited
    await route.fulfill({
      json: { status: 'ok', changes: [CLOSE_CEN, CLOSE_AIR], removed: [], replaced: [], added: 1, message: 'Done.' },
    })
  })
  await page.goto('/?s=close:CEN')
  await ask(page, 'and also the airport')
  await page.getByRole('button', { name: 'Remove change 1' }).click() // edit while the AI "thinks"
  release()

  await expect(page.getByText('The list changed while the AI was thinking')).toBeVisible()
  await expect(page.getByText('Close Airport')).toHaveCount(0)
  await expect(page.getByText('No changes yet.', { exact: false })).toBeVisible()
})
