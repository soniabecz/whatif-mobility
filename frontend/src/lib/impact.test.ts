import { describe, expect, it } from 'vitest'

import type { StopImpact } from '../types/simulation'
import {
  IMPACT_ORDER,
  IMPACT_STYLES,
  describeImpact,
  describeTimeModel,
  formatChange,
  formatMinutes,
  formatShare,
  impactLevel,
} from './impact'

function impact(overrides: Partial<StopImpact> = {}): StopImpact {
  return {
    stop_id: 'CEN',
    closed: false,
    affected_journeys: 0,
    impossible_journeys: 0,
    average_change_min: null,
    ...overrides,
  }
}

describe('impactLevel', () => {
  it('is unaffected when the stop has no impact entry', () => {
    expect(impactLevel(undefined)).toBe('unaffected')
  })

  it('is unaffected when no journeys changed', () => {
    expect(impactLevel(impact())).toBe('unaffected')
  })

  it('puts a closed stop first, whatever its numbers', () => {
    expect(impactLevel(impact({ closed: true, affected_journeys: 5, impossible_journeys: 3 }))).toBe(
      'closed',
    )
  })

  it('reports impossible journeys before slower or faster ones', () => {
    expect(
      impactLevel(impact({ affected_journeys: 4, impossible_journeys: 1, average_change_min: -2 })),
    ).toBe('impossible')
  })

  it('classifies mixed journeys by their average change', () => {
    expect(impactLevel(impact({ affected_journeys: 3, average_change_min: 1.5 }))).toBe('slower')
    expect(impactLevel(impact({ affected_journeys: 3, average_change_min: -0.5 }))).toBe('faster')
  })

  it('treats a zero or missing average as slower, never as faster', () => {
    expect(impactLevel(impact({ affected_journeys: 2, average_change_min: 0 }))).toBe('slower')
    expect(impactLevel(impact({ affected_journeys: 2, average_change_min: null }))).toBe('slower')
  })
})

describe('impact styles', () => {
  it('has a label, colour and icon for every level, in legend order', () => {
    expect(new Set(IMPACT_ORDER)).toEqual(new Set(Object.keys(IMPACT_STYLES)))
    for (const level of IMPACT_ORDER) {
      const style = IMPACT_STYLES[level]
      expect(style.label).not.toBe('')
      expect(style.icon).not.toBe('')
      expect(style.color).toMatch(/^#[0-9a-f]{6}$/)
    }
  })
})

describe('formatting', () => {
  it('formats minutes with one decimal', () => {
    expect(formatMinutes(12)).toBe('12.0 min')
    expect(formatMinutes(3.46)).toBe('3.5 min')
  })

  it('signs a change: + slower, − (minus sign) faster, ± none', () => {
    expect(formatChange(2.25)).toBe('+2.3 min')
    expect(formatChange(-4)).toBe('−4.0 min')
    expect(formatChange(0)).toBe('±0.0 min')
  })
})

describe('describeImpact', () => {
  it('says nothing changed for an unaffected stop', () => {
    expect(describeImpact(undefined)).toBe('No journeys affected')
    expect(describeImpact(impact())).toBe('No journeys affected')
  })

  it('explains a closed stop', () => {
    expect(describeImpact(impact({ closed: true }))).toBe(
      'Closed: no boarding, alighting or transfers',
    )
  })

  it('lists affected, impossible and the average change', () => {
    expect(
      describeImpact(impact({ affected_journeys: 6, impossible_journeys: 2, average_change_min: 3 })),
    ).toBe('6 journeys affected, 2 impossible, average +3.0 min')
  })

  it('leaves out parts that do not apply', () => {
    expect(describeImpact(impact({ affected_journeys: 4, average_change_min: -1.2 }))).toBe(
      '4 journeys affected, average −1.2 min',
    )
    expect(describeImpact(impact({ affected_journeys: 3, impossible_journeys: 3 }))).toBe(
      '3 journeys affected, 3 impossible',
    )
  })
})

describe('formatShare', () => {
  it('shows a backend share with one decimal', () => {
    expect(formatShare(11.8)).toBe('11.8%')
    expect(formatShare(0)).toBe('0.0%')
    expect(formatShare(100)).toBe('100.0%')
  })
})

describe('describeTimeModel', () => {
  it('says the waits come from the real timetable', () => {
    expect(describeTimeModel(true, 2)).toContain('from the real timetable')
    expect(describeTimeModel(true, 2)).not.toContain('invented')
  })

  it('mentions waiting only when it is modelled', () => {
    expect(describeTimeModel(true, 2)).toContain('waiting (half the time between buses')
    expect(describeTimeModel(true, 2)).toContain('2 min per change of bus')
    expect(describeTimeModel(false, 5)).toBe(
      'Journey times include 5 min per change of bus; waiting is not modelled.',
    )
  })
})
