// Save, load, overwrite, compare and delete scenarios (Day 13), against the real
// backend. Names are unique per run and everything saved here is deleted again
// afterwards, so the local database is left as it was.

import { expect, test, type APIRequestContext, type Page } from '@playwright/test'

const API = 'http://localhost:8000'
const CLOSE_CEN = { type: 'close_stop', stop_id: 'CEN' }
const SLOW = { type: 'change_travel_time', from_stop_id: 'RIV', to_stop_id: 'EST', travel_time_min: 9, both_directions: true }

let prefix = ''
test.beforeEach(() => {
  prefix = `E2E ${Date.now()}`
})
test.afterEach(async ({ request }) => {
  const saved: { id: number; name: string }[] = await (await request.get(`${API}/api/scenarios`)).json()
  for (const scenario of saved.filter((s) => s.name.startsWith(prefix))) {
    await request.delete(`${API}/api/scenarios/${scenario.id}`)
  }
})

async function save(page: Page, name: string) {
  await page.getByRole('button', { name: 'Save', exact: true }).first().click()
  await page.getByLabel('Name of the saved scenario').fill(name)
}

function row(page: Page, name: string) {
  return page.getByRole('list', { name: 'Saved scenarios' }).getByRole('listitem').filter({ hasText: name })
}

async function savedChanges(request: APIRequestContext, name: string) {
  const saved: { id: number; name: string }[] = await (await request.get(`${API}/api/scenarios`)).json()
  const id = saved.find((s) => s.name === name)!.id
  return (await (await request.get(`${API}/api/scenarios/${id}`)).json()).changes
}

test('save, load, overwrite and delete a scenario', async ({ page, request }) => {
  const name = `${prefix} Central closed`
  await page.goto('/?s=close:CEN')
  await expect(page.getByText('Close Central Station')).toBeVisible()

  await save(page, name)
  await page.getByRole('button', { name: 'Save', exact: true }).last().click()
  await expect(page.getByText(`Saved as “${name}”.`)).toBeVisible()
  await expect(row(page, name)).toContainText('1 change')
  expect(await savedChanges(request, name)).toEqual([CLOSE_CEN])

  // Clear, then load it back.
  await page.getByRole('button', { name: 'Clear' }).click()
  await row(page, name).getByRole('button', { name: `Load ${name}` }).click()
  await expect(page.getByText(`Loaded “${name}” (1 change).`)).toBeVisible()
  await expect(page.getByText('Close Central Station')).toBeVisible()
  await expect(page).toHaveURL(/\?s=close:CEN$/)

  // Saving under the same name offers to overwrite it.
  await page.goto('/?s=time:RIV-EST:9~close:CEN')
  await save(page, name)
  await expect(page.getByText('A scenario with this name is saved already')).toBeVisible()
  await page.getByRole('button', { name: 'Overwrite' }).click()
  await expect(row(page, name)).toContainText('2 changes')
  expect(await savedChanges(request, name)).toEqual([SLOW, CLOSE_CEN])

  // Delete asks once more.
  await row(page, name).getByRole('button', { name: `Delete ${name}` }).click()
  await row(page, name).getByRole('button', { name: 'Delete?' }).click()
  await expect(row(page, name)).toHaveCount(0)
})

test('compare the current list with a saved scenario', async ({ page, request }) => {
  const name = `${prefix} Central closed`
  await request.post(`${API}/api/scenarios`, { data: { name, changes: [CLOSE_CEN] } })
  await page.goto('/?s=time:RIV-EST:9')
  await expect(row(page, name)).toBeVisible()

  const pickA = page.locator('label').filter({ hasText: /^Compare A/ }).locator('select')
  const pickB = page.locator('label').filter({ hasText: /^Compare B/ }).locator('select')
  await expect(pickA).toHaveValue('current')
  await pickB.selectOption({ label: name })
  await page.getByRole('button', { name: 'Compare A and B' }).click()

  const expected = await (await request.post(`${API}/api/comparisons`, { data: { a: [SLOW], b: [CLOSE_CEN] } })).json()
  const panel = page.getByRole('region', { name: 'Comparison' })
  await expect(panel).toContainText('Current list')
  await expect(panel).toContainText(name)
  const slower = panel.getByRole('row', { name: /^Slower/ })
  await expect(slower.getByRole('cell').nth(0)).toHaveText(String(expected.a.slower))
  await expect(slower.getByRole('cell').nth(1)).toHaveText(String(expected.b.slower))
  // Fewer slower journeys is better: the lower side is highlighted.
  const betterA = expected.a.slower < expected.b.slower
  await expect(slower.getByRole('cell').nth(betterA ? 0 : 1)).toHaveAttribute('data-better', 'true')
  await expect(panel.getByText(`(${expected.compared_journeys} journeys)`)).toBeVisible()
  const differences = panel.getByRole('table').filter({ hasText: 'Largest differences' }).locator('tbody tr')
  await expect(differences).toHaveCount(expected.largest_differences.length)

  // The comparison used the current list: editing the list closes it.
  await page.getByRole('button', { name: 'Remove change 1' }).click()
  await expect(panel).toHaveCount(0)
})
