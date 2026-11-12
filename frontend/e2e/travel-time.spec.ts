// Regression (found Day 11): with min 0.1 and step 0.5 the browser silently
// refused whole minutes on the Travel time tab, so nothing was added.

import { expect, test } from '@playwright/test'

test('the Travel time tab accepts whole and decimal minutes', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByText('Live', { exact: true })).toBeVisible()
  await page.getByRole('radio', { name: 'Travel time' }).click()
  const time = page.locator('label').filter({ hasText: /^New travel time/ }).locator('input')

  for (const [index, minutes] of ['3', '7.5'].entries()) {
    await time.fill(minutes)
    await page.getByRole('button', { name: 'Add to scenario' }).click()
    await expect(page.getByText(`${index + 1}/20`)).toBeVisible()
    await expect(page.getByText(`: ${minutes} min`)).toBeVisible()
  }
})
