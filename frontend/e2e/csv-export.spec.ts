// CSV export: the downloaded file holds exactly the backend's numbers.

import { readFile } from 'node:fs/promises'

import { expect, test } from '@playwright/test'

const API = 'http://localhost:8000'

interface JourneyChange {
  origin_id: string
  destination_id: string
  time_before_min: number
  time_after_min: number | null
  change_min: number | null
  status: string
}

test('download the changed journeys as CSV', async ({ page, request }) => {
  await page.goto('/?s=close:CEN')
  await page.getByRole('button', { name: 'Run simulation (1 change)' }).click()

  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: 'CSV', exact: true }).click()
  const download = await downloadPromise
  expect(download.suggestedFilename()).toBe('whatif-changed-journeys_close-CEN.csv')

  const text = await readFile(await download.path(), 'utf-8')
  expect(text.startsWith('﻿')).toBe(true) // BOM for Excel
  const [header, ...rows] = text.slice(1).trimEnd().split('\r\n')
  expect(header).toBe(
    'origin_id,origin_name,destination_id,destination_name,status,time_before_min,time_after_min,change_min',
  )

  // Compare every row with the backend's own result for the same scenario.
  const response = await request.post(`${API}/api/simulations`, {
    data: { changes: [{ type: 'close_stop', stop_id: 'CEN' }] },
  })
  const expected: JourneyChange[] = (await response.json()).changed_journeys
  expect(rows).toHaveLength(expected.length)

  const fromFile = new Map(
    rows.map((row) => {
      const [origin, , destination, , status, before, after, change] = row.split(',')
      return [`${origin}>${destination}`, { status, before, after, change }]
    }),
  )
  const asText = (value: number | null) => (value === null ? '' : String(value))
  for (const j of expected) {
    expect(fromFile.get(`${j.origin_id}>${j.destination_id}`)).toEqual({
      status: j.status,
      before: asText(j.time_before_min),
      after: asText(j.time_after_min),
      change: asText(j.change_min),
    })
  }
})
