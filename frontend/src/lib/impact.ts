// How a stop's simulation result is shown: one level, one colour, one label.
// The numbers themselves always come from the backend.

import type { JourneyChange, StopImpact } from '../types/simulation'

export type ImpactLevel = 'closed' | 'impossible' | 'slower' | 'faster' | 'unaffected'

interface ImpactStyle {
  label: string
  color: string
  icon: string
}

// Fixed status palette (critical / warning / good) so a status colour never
// looks like a route colour's "series". Always shown with icon + label.
export const IMPACT_STYLES: Record<ImpactLevel, ImpactStyle> = {
  closed: { label: 'Closed stop', color: '#3f3f46', icon: '⊘' },
  impossible: { label: 'Some journeys impossible', color: '#d03b3b', icon: '✕' },
  slower: { label: 'Journeys slower', color: '#fab219', icon: '▲' },
  faster: { label: 'Journeys faster', color: '#0ca30c', icon: '▼' },
  unaffected: { label: 'Unaffected', color: '#a1a1aa', icon: '•' },
}

export const IMPACT_ORDER: ImpactLevel[] = [
  'closed',
  'impossible',
  'slower',
  'faster',
  'unaffected',
]

export function impactLevel(impact: StopImpact | undefined): ImpactLevel {
  if (!impact) return 'unaffected'
  if (impact.closed) return 'closed'
  if (impact.impossible_journeys > 0) return 'impossible'
  if (impact.affected_journeys === 0) return 'unaffected'
  // Mixed slower/faster journeys are classified by their average.
  return (impact.average_change_min ?? 0) < 0 ? 'faster' : 'slower'
}

export function formatMinutes(value: number): string {
  return `${value.toFixed(1)} min`
}

/** One sentence on what journey times include (the model the backend used).
 *  `realTimetable`: headways come from a real feed, not the invented sample. */
export function describeTimeModel(
  includeWaiting: boolean,
  transferPenaltyMin: number,
  realTimetable = false,
): string {
  const penalty = `${transferPenaltyMin} min per change of bus`
  const timetable = realTimetable ? 'from the real timetable' : 'an invented timetable'
  return includeWaiting
    ? `Journey times include waiting (half the time between buses, ${timetable}) at every boarding and ${penalty}.`
    : `Journey times include ${penalty}; waiting is not modelled.`
}

/** A share of trips computed by the backend, e.g. "11.8%". */
export function formatShare(pct: number): string {
  return `${pct.toFixed(1)}%`
}

/** Invented stop activity levels (demand weighting), as words. */
export const ACTIVITY_LABELS: Record<number, string> = { 1: 'quiet', 2: 'medium', 3: 'major' }

export function formatChange(value: number): string {
  const sign = value > 0 ? '+' : value < 0 ? '−' : '±'
  return `${sign}${Math.abs(value).toFixed(1)} min`
}

export function describeImpact(impact: StopImpact | undefined): string {
  const level = impactLevel(impact)
  if (!impact || level === 'unaffected') return 'No journeys affected'
  if (level === 'closed') return 'Closed: no boarding, alighting or transfers'
  const parts = [`${impact.affected_journeys} journeys affected`]
  if (impact.impossible_journeys > 0) parts.push(`${impact.impossible_journeys} impossible`)
  if (impact.average_change_min !== null) {
    parts.push(`average ${formatChange(impact.average_change_min)}`)
  }
  return parts.join(', ')
}

/** Table and CSV order: impossible journeys first, then the largest changes. */
export function compareJourneys(a: JourneyChange, b: JourneyChange): number {
  if ((a.status === 'impossible') !== (b.status === 'impossible')) {
    return a.status === 'impossible' ? -1 : 1
  }
  return Math.abs(b.change_min ?? 0) - Math.abs(a.change_min ?? 0)
}
