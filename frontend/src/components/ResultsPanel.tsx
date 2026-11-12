import { useMemo, useState, type ReactNode } from 'react'
import {
  ChartColumn,
  ChevronDown,
  ChevronUp,
  Clock,
  Route as RouteIcon,
  type LucideIcon,
} from 'lucide-react'

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
import { IMPACT_ICONS } from './impactIcons'
import type { JourneySelection } from './JourneyExplorer'
import { ResultsChart } from './ResultsChart'
import { Button } from './ui/Button'
import { SectionTitle } from './ui/SectionTitle'
import { SegmentedControl } from './ui/SegmentedControl'
import { cx } from './ui/cx'

export type ResultsTab = 'summary' | 'journey'

interface ResultsPanelProps {
  result: SimulationResult
  stops: Map<string, Stop>
  tab: ResultsTab
  onTabChange: (tab: ResultsTab) => void
  /** Called when a row of the changed-journeys table is clicked. */
  onSelectJourney: (selection: JourneySelection) => void
  /** Rendered in the Journey tab. */
  journeyExplorer: ReactNode
}

const TABS = [
  { value: 'summary' as const, label: 'Summary', icon: ChartColumn },
  { value: 'journey' as const, label: 'Journey', icon: RouteIcon },
]

const TABLE_PREVIEW_ROWS = 10

const STATUS_TEXT: Record<JourneyStatus, { label: string; className: string }> = {
  impossible: { label: 'Impossible', className: 'text-red-700' },
  slower: { label: 'Slower', className: 'text-amber-700' },
  faster: { label: 'Faster', className: 'text-green-700' },
}

/** Impossible journeys first, then the largest changes. */
function compareJourneys(a: JourneyChange, b: JourneyChange): number {
  if ((a.status === 'impossible') !== (b.status === 'impossible')) {
    return a.status === 'impossible' ? -1 : 1
  }
  return Math.abs(b.change_min ?? 0) - Math.abs(a.change_min ?? 0)
}

interface KpiProps {
  icon: LucideIcon
  /** Status colour for the icon only; numbers stay in text colours. */
  color: string
  label: string
  value: string
  hint?: string
}

function Kpi({ icon: Icon, color, label, value, hint }: KpiProps) {
  return (
    // Named group: screen readers (and the e2e test) read "Slower: 12" as one unit.
    <div role="group" aria-label={label} className="rounded-xl border border-line bg-white px-3 py-2.5">
      <p className="flex items-center gap-1.5 text-[11px] font-semibold text-ink-muted">
        <Icon size={13} style={{ color }} aria-hidden />
        {label}
      </p>
      <p className="mt-0.5 text-xl font-semibold text-ink tabular-nums">{value}</p>
      {hint && <p className="text-[11px] text-ink-subtle tabular-nums">{hint}</p>}
    </div>
  )
}

function DetailRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex justify-between gap-3 py-1.5">
      <dt className="text-ink-muted">{label}</dt>
      <dd className="text-right font-medium text-ink tabular-nums">{children}</dd>
    </div>
  )
}

export function ResultsPanel({
  result,
  stops,
  tab,
  onTabChange,
  onSelectJourney,
  journeyExplorer,
}: ResultsPanelProps) {
  const [expanded, setExpanded] = useState(false)
  const [showAll, setShowAll] = useState(false)
  const { summary } = result
  const name = (id: string) => stopLabel(stops, id)

  const sortedJourneys = useMemo(
    () => [...result.changed_journeys].sort(compareJourneys),
    [result],
  )
  const visibleJourneys = showAll ? sortedJourneys : sortedJourneys.slice(0, TABLE_PREVIEW_ROWS)
  const impacts = new Map(result.stop_impacts.map((i) => [i.stop_id, i]))

  function select(journey: JourneyChange) {
    onSelectJourney({ originId: journey.origin_id, destinationId: journey.destination_id })
  }

  return (
    <section className="space-y-3">
      <SectionTitle
        icon={ChartColumn}
        aside={
          tab === 'summary' && (
            <Button
              variant="ghost"
              size="sm"
              icon={expanded ? ChevronDown : ChevronUp}
              onClick={() => setExpanded(!expanded)}
              aria-expanded={expanded}
            >
              {expanded ? 'Less' : 'Details'}
            </Button>
          )
        }
      >
        Results
        <span className="text-xs font-normal text-ink-subtle">
          {summary.total_journeys} journeys
        </span>
      </SectionTitle>

      <SegmentedControl label="Results view" options={TABS} value={tab} onChange={onTabChange} />

      {tab === 'journey' && journeyExplorer}

      {tab === 'summary' && (
      <>
      <p className="text-[11px] text-ink-subtle">
        Journey times include {summary.transfer_penalty_min} min per change of bus.
      </p>
      <div className="grid grid-cols-2 gap-2">
        <Kpi
          icon={IMPACT_ICONS.slower}
          color={IMPACT_STYLES.slower.color}
          label="Slower"
          value={String(summary.slower)}
        />
        <Kpi
          icon={IMPACT_ICONS.faster}
          color={IMPACT_STYLES.faster.color}
          label="Faster"
          value={String(summary.faster)}
        />
        <Kpi
          icon={IMPACT_ICONS.impossible}
          color={IMPACT_STYLES.impossible.color}
          label="Impossible"
          value={String(summary.impossible)}
        />
        <Kpi
          icon={Clock}
          color="var(--color-accent)"
          label="Avg journey time"
          value={
            summary.average_time_after_min === null
              ? '–'
              : formatMinutes(summary.average_time_after_min)
          }
          hint={
            summary.average_time_before_min === null
              ? undefined
              : `was ${formatMinutes(summary.average_time_before_min)}`
          }
        />
      </div>

      {expanded && (
        <div className="space-y-5 pt-1">
          <dl className="divide-y divide-line rounded-xl border border-line bg-white px-3 text-sm">
            <DetailRow label="Unchanged">{summary.unchanged}</DetailRow>
            <DetailRow label="To/from closed stops (not counted)">
              {summary.to_or_from_closed_stop}
            </DetailRow>
            <DetailRow label="Total change, all possible journeys">
              {formatChange(summary.total_time_change_min)}
            </DetailRow>
            {summary.largest_increase && summary.largest_increase.change_min !== null && (
              <DetailRow label="Largest increase">
                {name(summary.largest_increase.origin_id)} →{' '}
                {name(summary.largest_increase.destination_id)} (
                {formatChange(summary.largest_increase.change_min)})
              </DetailRow>
            )}
          </dl>

          {result.most_affected_stop_ids.length > 0 && (
            <div>
              <h3 className="text-xs font-semibold text-ink-muted">Most affected stops</h3>
              <ol className="mt-2 space-y-1.5">
                {result.most_affected_stop_ids.map((id) => {
                  const impact = impacts.get(id)
                  const level = impactLevel(impact)
                  const Icon = IMPACT_ICONS[level]
                  return (
                    <li key={id} className="flex items-start gap-2.5 text-sm">
                      <span
                        className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-white"
                        style={{ backgroundColor: IMPACT_STYLES[level].color }}
                      >
                        <Icon size={13} aria-hidden />
                      </span>
                      <span>
                        <span className="font-medium text-ink">{name(id)}</span>
                        <span className="block text-xs text-ink-muted">
                          {IMPACT_STYLES[level].label} · {describeImpact(impact)}
                        </span>
                      </span>
                    </li>
                  )
                })}
              </ol>
            </div>
          )}

          <ResultsChart journeys={result.changed_journeys} stops={stops} />

          <div>
            <h3 className="text-xs font-semibold text-ink-muted">
              Changed journeys ({sortedJourneys.length})
              <span className="ml-1 font-normal text-ink-subtle">· click one to explore</span>
            </h3>
            {sortedJourneys.length === 0 ? (
              <p className="mt-1 text-sm text-ink-subtle">No journey changed.</p>
            ) : (
              <>
                <div className="mt-2 overflow-x-auto rounded-xl border border-line bg-white">
                  <table className="w-full text-left text-sm">
                    <thead className="bg-surface-muted text-[11px] text-ink-muted">
                      <tr>
                        <th className="px-3 py-2 font-semibold">From → To</th>
                        <th className="px-2 py-2 text-right font-semibold">Before</th>
                        <th className="px-2 py-2 text-right font-semibold">After</th>
                        <th className="px-3 py-2 text-right font-semibold">Change</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-line tabular-nums">
                      {visibleJourneys.map((j) => {
                        const status = STATUS_TEXT[j.status]
                        const Icon = IMPACT_ICONS[j.status]
                        return (
                          <tr
                            key={`${j.origin_id}-${j.destination_id}`}
                            className="cursor-pointer hover:bg-accent-soft/60"
                            onClick={() => select(j)}
                          >
                            <td className="px-3 py-1.5 text-ink">
                              {/* A real button keeps rows reachable by keyboard. */}
                              <button
                                type="button"
                                className="text-left hover:text-accent focus-visible:text-accent focus-visible:outline-none"
                                title="Show this journey on the map"
                                onClick={(event) => {
                                  event.stopPropagation()
                                  select(j)
                                }}
                              >
                                {name(j.origin_id)} → {name(j.destination_id)}
                              </button>
                            </td>
                            <td className="px-2 py-1.5 text-right text-ink-muted">
                              {j.time_before_min.toFixed(1)}
                            </td>
                            <td className="px-2 py-1.5 text-right text-ink-muted">
                              {j.time_after_min === null ? '–' : j.time_after_min.toFixed(1)}
                            </td>
                            <td
                              className={cx(
                                'px-3 py-1.5 text-right font-medium whitespace-nowrap',
                                status.className,
                              )}
                            >
                              <Icon size={12} className="mr-1 inline" aria-hidden />
                              {j.change_min === null ? status.label : formatChange(j.change_min)}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
                {sortedJourneys.length > TABLE_PREVIEW_ROWS && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="mt-2"
                    onClick={() => setShowAll(!showAll)}
                  >
                    {showAll ? 'Show fewer' : `Show all ${sortedJourneys.length}`}
                  </Button>
                )}
              </>
            )}
          </div>
        </div>
      )}
      </>
      )}
    </section>
  )
}
