// CSV export of the changed journeys. Values are written exactly as the
// backend computed them; nothing is calculated here.

import type { Stop } from '../types/network'
import type { ScenarioChange } from '../types/scenario'
import type { JourneyChange } from '../types/simulation'
import { compareJourneys } from './impact'
import { stopLabel } from './network'
import { encodeChanges } from './shareLink'

export const CSV_COLUMNS = [
  'origin_id',
  'origin_name',
  'destination_id',
  'destination_name',
  'status',
  'time_before_min',
  'time_after_min',
  'change_min',
] as const

/** Quote a field when it contains a comma, quote or line break (RFC 4180). */
function field(value: string | number | null): string {
  if (value === null) return '' // impossible journeys have no "after" time
  const text = String(value)
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

/** One row per changed journey, in the results table's order. */
export function changedJourneysCsv(journeys: JourneyChange[], stops: Map<string, Stop>): string {
  const rows = [...journeys].sort(compareJourneys).map((j) =>
    [
      j.origin_id,
      stopLabel(stops, j.origin_id),
      j.destination_id,
      stopLabel(stops, j.destination_id),
      j.status,
      j.time_before_min,
      j.time_after_min,
      j.change_min,
    ]
      .map(field)
      .join(','),
  )
  // CRLF line endings, as RFC 4180 specifies and Excel expects.
  return [CSV_COLUMNS.join(','), ...rows].join('\r\n') + '\r\n'
}

const MAX_NAME_CODE = 60

/**
 * File name from the scenario's share code, e.g.
 * whatif-changed-journeys_close-CEN_remove-MKT-UNI.csv.
 * Long scenarios fall back to a timestamp.
 */
export function csvFileName(changes: ScenarioChange[], now: Date = new Date()): string {
  const code = encodeChanges(changes)
    .replace(/~/g, '_')
    .replace(/[^A-Za-z0-9._-]+/g, '-')
  if (code !== '' && code.length <= MAX_NAME_CODE) return `whatif-changed-journeys_${code}.csv`
  const pad = (n: number) => String(n).padStart(2, '0')
  const stamp = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}`
  return `whatif-changed-journeys_${stamp}.csv`
}

/** Let the browser save the text as a file. */
export function downloadCsv(fileName: string, csv: string): void {
  // The BOM tells Excel the file is UTF-8, so stop names keep their accents.
  const blob = new Blob(['﻿', csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = fileName
  link.click()
  // Some browsers start the download asynchronously: release the URL a bit later.
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}
