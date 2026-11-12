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

/** One sentence on what journey times include (the model the backend used). */
export function describeTimeModel(includeWaiting: boolean, transferPenaltyMin: number): string {
  const penalty = `${transferPenaltyMin} min per change of bus`
  return includeWaiting
    ? `Journey times include waiting (half the time between buses, an invented timetable) at every boarding and ${penalty}.`
    : `Journey times include ${penalty}; waiting is not modelled.`
}

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
