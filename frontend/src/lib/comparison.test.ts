import { describe, expect, it } from 'vitest'

import type { SimulationSummary } from '../types/simulation'
import { betterSide, comparisonRows, formatValue } from './comparison'

describe('betterSide', () => {
  it('follows the direction of the figure', () => {
    expect(betterSide({ a: 3, b: 5, better: 'lower' })).toBe('a')
    expect(betterSide({ a: 3, b: 5, better: 'higher' })).toBe('b')
  })

  it('has no winner for equal or missing values', () => {
    expect(betterSide({ a: 4, b: 4, better: 'lower' })).toBeNull()
    expect(betterSide({ a: null, b: 4, better: 'lower' })).toBeNull()
  })
})

describe('comparisonRows', () => {
  const summary = (overrides: Partial<SimulationSummary>): SimulationSummary =>
    ({
      slower: 0, faster: 0, impossible: 0, newly_possible: 0,
      average_time_before_min: 20, average_time_after_min: 20,
      demand_weighted: { slower_pct: 0, faster_pct: 0 },
      ...overrides,
    }) as SimulationSummary

  it('puts each side next to its own "before" average', () => {
    const rows = comparisonRows(
      summary({ slower: 30, average_time_before_min: 21.6, average_time_after_min: 23.2 }),
      summary({ faster: 22, average_time_before_min: 21.6, average_time_after_min: 21.2 }),
    )
    const avg = rows.find((row) => row.label === 'Avg journey time')!
    expect([avg.a, avg.wasA, avg.b, avg.wasB]).toEqual([23.2, 21.6, 21.2, 21.6])
    expect(betterSide(avg)).toBe('b')
    expect(betterSide(rows.find((row) => row.label === 'Slower')!)).toBe('b')
    expect(betterSide(rows.find((row) => row.label === 'Faster')!)).toBe('b')
  })

  it('shows a missing average as a dash', () => {
    const rows = comparisonRows(summary({ average_time_after_min: null }), summary({}))
    const avg = rows.find((row) => row.label === 'Avg journey time')!
    expect(formatValue(avg.a, avg.unit)).toBe('—')
    expect(betterSide(avg)).toBeNull()
  })
})

describe('formatValue', () => {
  it('formats counts, minutes and shares', () => {
    expect(formatValue(30)).toBe('30')
    expect(formatValue(21.25, 'min')).toBe('21.3 min')
    expect(formatValue(7.2, '%')).toBe('7.2%')
  })
})
