import { useMemo, useState } from 'react'

import {
  IMPACT_STYLES,
  describeImpact,
  formatChange,
  formatMinutes,
  impactLevel,
} from '../lib/impact'
import { stopLabel } from '../lib/network'
import type { Stop } from '../types/network'
import type { JourneyChange, JourneyStatus, SimulationResult } from '../types/simulation'
import { ResultsChart } from './ResultsChart'

interface ResultsPanelProps {
  result: SimulationResult
  stops: Map<string, Stop>
}

const TABLE_PREVIEW_ROWS = 10

const STATUS_TEXT: Record<JourneyStatus, { icon: string; label: string; className: string }> = {
  impossible: { icon: '✕', label: 'Impossible', className: 'text-red-700' },
  slower: { icon: '▲', label: 'Slower', className: 'text-amber-700' },
  faster: { icon: '▼', label: 'Faster', className: 'text-green-700' },
}

/** Impossible journeys first, then the largest changes. */
function compareJourneys(a: JourneyChange, b: JourneyChange): number {
  if ((a.status === 'impossible') !== (b.status === 'impossible')) {
    return a.status === 'impossible' ? -1 : 1
  }
  return Math.abs(b.change_min ?? 0) - Math.abs(a.change_min ?? 0)
}

function StatTile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-md border border-slate-200 bg-white p-2">
      <p className="text-xs text-slate-500">{label}</p>
      <p className="text-lg font-semibold tabular-nums">{value}</p>
      {hint && <p className="text-xs text-slate-500">{hint}</p>}
    </div>
  )
}

export function ResultsPanel({ result, stops }: ResultsPanelProps) {
  const [showAll, setShowAll] = useState(false)
  const { summary } = result
  const name = (id: string) => stopLabel(stops, id)

  const sortedJourneys = useMemo(
    () => [...result.changed_journeys].sort(compareJourneys),
    [result],
  )
  const visibleJourneys = showAll ? sortedJourneys : sortedJourneys.slice(0, TABLE_PREVIEW_ROWS)
  const impacts = new Map(result.stop_impacts.map((i) => [i.stop_id, i]))

  const averages =
    summary.average_time_before_min !== null && summary.average_time_after_min !== null
      ? `${formatMinutes(summary.average_time_before_min)} → ${formatMinutes(summary.average_time_after_min)}`
      : '–'

  return (
    <section className="space-y-5">
      <h2 className="text-sm font-semibold tracking-wide text-slate-500 uppercase">2. Results</h2>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        <StatTile label="Journeys (stop pairs)" value={String(summary.total_journeys)} />
        <StatTile label="▲ Slower" value={String(summary.slower)} />
        <StatTile label="▼ Faster" value={String(summary.faster)} />
        <StatTile label="✕ Impossible" value={String(summary.impossible)} />
        <StatTile label="Unchanged" value={String(summary.unchanged)} />
        <StatTile
          label="⊘ To/from closed stop"
          value={String(summary.to_or_from_closed_stop)}
          hint="not counted elsewhere"
        />
      </div>

      <dl className="space-y-1 text-sm">
        <div className="flex justify-between gap-2">
          <dt className="text-slate-600">Average journey time</dt>
          <dd className="font-medium tabular-nums">{averages}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt className="text-slate-600">Total change (all possible journeys)</dt>
          <dd className="font-medium tabular-nums">{formatChange(summary.total_time_change_min)}</dd>
        </div>
        {summary.largest_increase && summary.largest_increase.change_min !== null && (
          <div className="flex justify-between gap-2">
            <dt className="text-slate-600">Largest increase</dt>
            <dd className="text-right font-medium">
              {name(summary.largest_increase.origin_id)} →{' '}
              {name(summary.largest_increase.destination_id)}{' '}
              <span className="tabular-nums">
                ({formatChange(summary.largest_increase.change_min)})
              </span>
            </dd>
          </div>
        )}
      </dl>

      {result.most_affected_stop_ids.length > 0 && (
        <div>
          <h3 className="text-sm font-medium">Most affected stops</h3>
          <ol className="mt-1 space-y-1">
            {result.most_affected_stop_ids.map((id) => {
              const impact = impacts.get(id)
              const style = IMPACT_STYLES[impactLevel(impact)]
              return (
                <li key={id} className="flex items-start gap-2 text-sm">
                  <span
                    className="mt-1 h-3 w-3 shrink-0 rounded-full"
                    style={{ backgroundColor: style.color }}
                  />
                  <span>
                    <span className="font-medium">{name(id)}</span>
                    <span className="text-slate-600"> – {style.icon} {describeImpact(impact)}</span>
                  </span>
                </li>
              )
            })}
          </ol>
        </div>
      )}

      <ResultsChart journeys={result.changed_journeys} stops={stops} />

      <div>
        <h3 className="text-sm font-medium">Changed journeys ({sortedJourneys.length})</h3>
        {sortedJourneys.length === 0 ? (
          <p className="mt-1 text-sm text-slate-500">No journey changed.</p>
        ) : (
          <>
            <div className="mt-2 overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-slate-200 text-xs text-slate-500">
                  <tr>
                    <th className="py-1 pr-2 font-medium">From → To</th>
                    <th className="py-1 pr-2 text-right font-medium">Before</th>
                    <th className="py-1 pr-2 text-right font-medium">After</th>
                    <th className="py-1 text-right font-medium">Change</th>
                  </tr>
                </thead>
                <tbody className="tabular-nums">
                  {visibleJourneys.map((j) => {
                    const status = STATUS_TEXT[j.status]
                    return (
                      <tr key={`${j.origin_id}-${j.destination_id}`} className="border-b border-slate-100">
                        <td className="py-1 pr-2">
                          {name(j.origin_id)} → {name(j.destination_id)}
                        </td>
                        <td className="py-1 pr-2 text-right">{j.time_before_min.toFixed(1)}</td>
                        <td className="py-1 pr-2 text-right">
                          {j.time_after_min === null ? '–' : j.time_after_min.toFixed(1)}
                        </td>
                        <td className={`py-1 text-right font-medium ${status.className}`}>
                          {j.change_min === null
                            ? `${status.icon} ${status.label}`
                            : `${status.icon} ${formatChange(j.change_min)}`}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            {sortedJourneys.length > TABLE_PREVIEW_ROWS && (
              <button
                type="button"
                onClick={() => setShowAll(!showAll)}
                className="mt-2 text-sm text-blue-700 hover:underline"
              >
                {showAll ? 'Show fewer' : `Show all ${sortedJourneys.length}`}
              </button>
            )}
          </>
        )}
      </div>
    </section>
  )
}
