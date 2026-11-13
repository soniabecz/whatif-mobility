import { describe, expect, it } from 'vitest'

import { csvFileName } from './exportCsv'

// The CSV itself is written by the backend: see backend/tests/test_changed_journeys_limit.py.

describe('csvFileName', () => {
  it('names the file after the scenario', () => {
    expect(
      csvFileName([
        { type: 'close_stop', stop_id: 'CEN' },
        { type: 'remove_connection', from_stop_id: 'MKT', to_stop_id: 'UNI', both_directions: false },
      ]),
    ).toBe('whatif-changed-journeys_close-CEN_remove-MKT-UNI-oneway.csv')
  })

  it('keeps only file-name-safe characters', () => {
    expect(csvFileName([{ type: 'close_stop', stop_id: 'A/B é' }])).toMatch(
      /^whatif-changed-journeys_[A-Za-z0-9._-]+\.csv$/,
    )
  })

  it('uses a timestamp for long scenarios', () => {
    const many = Array.from({ length: 20 }, () => ({ type: 'close_stop' as const, stop_id: 'CEN' }))
    expect(csvFileName(many, new Date(2026, 10, 12, 9, 5))).toBe(
      'whatif-changed-journeys_20261112-0905.csv',
    )
  })
})
