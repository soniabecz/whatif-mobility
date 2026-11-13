// Pure helpers for the comparison card (Day 13). The numbers come from the
// backend; this only decides which side reads as better and how to show it.

import type { SimulationSummary } from '../types/simulation'

export type Side = 'a' | 'b'

export interface ComparisonRow {
  label: string
  a: number | null
  b: number | null
  /** What "better" means for this figure. */
  better: 'lower' | 'higher'
  /** Shown under the value: the side's own "before" figure, if any. */
  wasA?: number | null
  wasB?: number | null
  unit?: 'min' | '%'
}

/** The better side, or null when equal, unknown, or not comparable. */
export function betterSide(row: Pick<ComparisonRow, 'a' | 'b' | 'better'>): Side | null {
  if (row.a === null || row.b === null || Math.abs(row.a - row.b) < 1e-9) return null
  const aIsLower = row.a < row.b
  return (row.better === 'lower') === aIsLower ? 'a' : 'b'
}

/** The figures shown side by side, each side measured against today's network. */
export function comparisonRows(a: SimulationSummary, b: SimulationSummary): ComparisonRow[] {
  return [
    { label: 'Slower', a: a.slower, b: b.slower, better: 'lower' },
    { label: 'Faster', a: a.faster, b: b.faster, better: 'higher' },
    { label: 'Impossible', a: a.impossible, b: b.impossible, better: 'lower' },
    { label: 'Newly possible', a: a.newly_possible, b: b.newly_possible, better: 'higher' },
    {
      label: 'Avg journey time',
      a: a.average_time_after_min ?? null,
      b: b.average_time_after_min ?? null,
      wasA: a.average_time_before_min ?? null,
      wasB: b.average_time_before_min ?? null,
      better: 'lower',
      unit: 'min',
    },
    {
      label: 'Trips slower (demand)',
      a: a.demand_weighted.slower_pct,
      b: b.demand_weighted.slower_pct,
      better: 'lower',
      unit: '%',
    },
    {
      label: 'Trips faster (demand)',
      a: a.demand_weighted.faster_pct,
      b: b.demand_weighted.faster_pct,
      better: 'higher',
      unit: '%',
    },
  ]
}

export function formatValue(value: number | null | undefined, unit?: 'min' | '%'): string {
  if (value === null || value === undefined) return '—'
  if (unit === 'min') return `${value.toFixed(1)} min`
  if (unit === '%') return `${value.toFixed(1)}%`
  return String(value)
}
