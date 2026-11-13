// CSV export of the changed journeys: the backend writes the file
// (POST /api/simulations/csv, every journey); here only its name and the download.

import type { ScenarioChange } from '../types/scenario'
import { encodeChanges } from './shareLink'

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
