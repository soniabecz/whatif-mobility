// Shareable links: the change list lives in the URL (?s=...).

import { expect, test } from '@playwright/test'

const SHARED = 'close:CEN~remove:MKT-UNI~time:RIV-EST:9:oneway'

test('opening a shared link restores the changes; edits update the URL', async ({
  page,
  context,
}) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  await page.goto(`/?s=${SHARED}`)

  // Restored, in order, but not run: the user checks them first.
  await expect(page.getByRole('status')).toContainText('Loaded 3 changes from a shared link')
  const items = page.getByRole('listitem').filter({ has: page.getByRole('button', { name: /^Remove change/ }) })
  await expect(items).toHaveCount(3)
  await expect(items.nth(0)).toContainText('Close Central Station')
  await expect(items.nth(2)).toContainText('→') // one way
  await expect(items.nth(2)).toContainText('9 min')
  await expect(page.getByRole('button', { name: 'Run simulation (3 changes)' })).toBeEnabled()
  await expect(page.getByText('Slower')).toHaveCount(0)

  // Adding a change updates the address bar (and hides the notice).
  await page.getByRole('radio', { name: 'Close stop' }).click()
  await page.locator('label').filter({ hasText: /^Stop/ }).locator('select').selectOption('UNI')
  await page.getByRole('button', { name: 'Add to scenario' }).click()
  await expect(page).toHaveURL(new RegExp(`\\?s=${SHARED}~close:UNI$`))
  await expect(page.getByRole('status')).toHaveCount(0)

  // Copy link puts exactly that URL on the clipboard.
  await page.getByRole('button', { name: 'Copy link' }).click()
  await expect(page.getByRole('button', { name: 'Copied' })).toBeVisible()
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(page.url())

  // Clearing the list removes the parameter.
  await page.getByRole('button', { name: 'Clear' }).click()
  await expect(page).toHaveURL(/\/$/)
})

test('an invalid link loads nothing and explains why', async ({ page }) => {
  await page.goto('/?s=close:CEN~close:XYZ')

  await expect(page.getByRole('alert')).toHaveText(
    'This link could not be opened: change 2: unknown stop "XYZ".',
  )
  await expect(page.getByText('No changes yet.')).toBeVisible()
  // The bad link stays visible in the address bar until the list is edited.
  await expect(page).toHaveURL(/\?s=close:CEN~close:XYZ$/)
})
