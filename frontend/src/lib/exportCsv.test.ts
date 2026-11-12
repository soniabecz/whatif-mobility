import { describe, expect, it } from 'vitest'

import { smallNetwork } from '../test/smallNetwork'
import type { Stop } from '../types/network'
import type { JourneyChange } from '../types/simulation'
import { CSV_COLUMNS, changedJourneysCsv, csvFileName } from './exportCsv'
import { stopsById } from './network'

const stops = stopsById(smallNetwork)

const slower: JourneyChange = {
  origin_id: 'ALP',
  destination_id: 'CAS',
  time_before_min: 6,
  time_after_min: 8.5,
  change_min: 2.5,
  status: 'slower',
}
const faster: JourneyChange = {
  origin_id: 'DUN',
  destination_id: 'ALP',
  time_before_min: 12.3,
  time_after_min: 7.3,
  change_min: -5,
  status: 'faster',
}
const impossible: JourneyChange = {
  origin_id: 'BRK',
  destination_id: 'DUN',
  time_before_min: 5,
  time_after_min: null,
  change_min: null,
  status: 'impossible',
}

const lines = (csv: string) => csv.split('\r\n')

describe('changedJourneysCsv', () => {
  it('starts with the header row', () => {
    expect(lines(changedJourneysCsv([], stops))[0]).toBe(CSV_COLUMNS.join(','))
  })

  it('writes the backend values unchanged, in the table order', () => {
    // Impossible first, then the largest change (5 before 2.5).
    expect(lines(changedJourneysCsv([slower, impossible, faster], stops))).toEqual([
      CSV_COLUMNS.join(','),
      'BRK,Brook Street,DUN,Dunes,impossible,5,,',
      'DUN,Dunes,ALP,Alpine Road,faster,12.3,7.3,-5',
      'ALP,Alpine Road,CAS,Castle,slower,6,8.5,2.5',
      '', // file ends with a line break
    ])
  })

  it('does not reorder the input array', () => {
    const input = [slower, impossible]
    changedJourneysCsv(input, stops)
    expect(input).toEqual([slower, impossible])
  })

  it('quotes names with commas, quotes or line breaks', () => {
    const odd = new Map<string, Stop>([
      ['ALP', { id: 'ALP', name: 'Main St, North', lat: 0, lon: 0, activity: 1 }],
      ['CAS', { id: 'CAS', name: 'The "Castle"\nGate', lat: 0, lon: 0, activity: 1 }],
    ])
    const csv = changedJourneysCsv([slower], odd)
    expect(csv).toContain(',"Main St, North",')
    expect(csv).toContain(',"The ""Castle""\nGate",')
  })

  it('falls back to the stop id for an unknown stop', () => {
    const row = lines(changedJourneysCsv([{ ...slower, origin_id: 'XYZ' }], stops))[1]
    expect(row.startsWith('XYZ,XYZ,')).toBe(true)
  })
})

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
