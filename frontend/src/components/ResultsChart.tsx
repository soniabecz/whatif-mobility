import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { formatChange, formatMinutes } from '../lib/impact'
import { stopLabel } from '../lib/network'
import type { Stop } from '../types/network'
import type { JourneyChange } from '../types/simulation'

// Categorical slots 1 and 2 of the validated reference palette (dataviz skill);
// both pass the CVD and contrast checks on the light surface.
const BEFORE_COLOR = '#2a78d6'
const AFTER_COLOR = '#eb6834'
const MAX_ROWS = 10
const ROW_HEIGHT = 34

interface ResultsChartProps {
  journeys: JourneyChange[]
  stops: Map<string, Stop>
}

interface ChartRow {
  label: string // short, for the axis
  fullLabel: string // full names, for the tooltip
  before: number
  after: number
  change: number
}

export function ResultsChart({ journeys, stops }: ResultsChartProps) {
  // Biggest changes among journeys that are still possible (impossible
  // journeys have no "after" time; they are counted in the summary tiles).
  const rows: ChartRow[] = journeys
    .filter((j) => j.time_after_min !== null && j.change_min !== null)
    .sort((a, b) => Math.abs(b.change_min ?? 0) - Math.abs(a.change_min ?? 0))
    .slice(0, MAX_ROWS)
    .map((j) => ({
      label: `${j.origin_id} → ${j.destination_id}`,
      fullLabel: `${stopLabel(stops, j.origin_id)} → ${stopLabel(stops, j.destination_id)}`,
      before: j.time_before_min,
      after: j.time_after_min ?? 0,
      change: j.change_min ?? 0,
    }))

  if (rows.length === 0) {
    return (
      <p className="text-sm text-ink-subtle">
        No journey that is still possible changed its travel time.
      </p>
    )
  }

  return (
    <figure className="rounded-xl border border-line bg-white p-3">
      <figcaption className="text-xs font-semibold text-ink-muted">
        Biggest changes in travel time (top {rows.length})
      </figcaption>
      <div style={{ height: rows.length * ROW_HEIGHT + 70 }} className="mt-2">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} layout="vertical" barGap={2} margin={{ left: 0, right: 12 }}>
            <CartesianGrid horizontal={false} stroke="#e3e5ea" />
            <XAxis
              type="number"
              unit=" min"
              tick={{ fontSize: 11, fill: '#475569' }}
              stroke="#e3e5ea"
            />
            <YAxis
              type="category"
              dataKey="label"
              width={84}
              tick={{ fontSize: 11, fill: '#475569' }}
              stroke="#e3e5ea"
            />
            <Tooltip
              cursor={{ fill: '#f4f5f7' }}
              content={({ active, payload }) => {
                const row = payload?.[0]?.payload as ChartRow | undefined
                if (!active || !row) return null
                return (
                  <div className="rounded-xl border border-line bg-white px-3 py-2 text-xs text-ink shadow-soft">
                    <p className="font-semibold">{row.fullLabel}</p>
                    <p>Before: {formatMinutes(row.before)}</p>
                    <p>After: {formatMinutes(row.after)}</p>
                    <p className="font-medium">Change: {formatChange(row.change)}</p>
                  </div>
                )
              }}
            />
            <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="before" name="Before" fill={BEFORE_COLOR} barSize={10} radius={[0, 4, 4, 0]} />
            <Bar dataKey="after" name="After" fill={AFTER_COLOR} barSize={10} radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </figure>
  )
}
