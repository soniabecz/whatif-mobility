import { useMemo, useState } from 'react'
import {
  ArrowLeftRight,
  ArrowRight,
  CircleSlash,
  Loader2,
  Repeat,
  TriangleAlert,
  X,
} from 'lucide-react'

import { IMPACT_STYLES, formatChange, formatMinutes } from '../lib/impact'
import { sortedStops, stopLabel, stopsById } from '../lib/network'
import type { JourneyComparison, JourneyComparisonStatus, JourneyPlan } from '../types/journey'
import type { Network, Route } from '../types/network'
import { IMPACT_ICONS } from './impactIcons'
import { Button } from './ui/Button'
import { Field, inputClass } from './ui/Field'
import { IconButton } from './ui/IconButton'
import { cx } from './ui/cx'

export interface JourneySelection {
  originId: string
  destinationId: string
}

export type JourneyState =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'success'; comparison: JourneyComparison }

interface JourneyExplorerProps {
  network: Network
  selection: JourneySelection | null
  state: JourneyState
  onSelect: (selection: JourneySelection) => void
  onClear: () => void
}

/** Parent remounts this (via `key`) when the selection changes from outside. */
export function JourneyExplorer({
  network,
  selection,
  state,
  onSelect,
  onClear,
}: JourneyExplorerProps) {
  const stops = useMemo(() => sortedStops(network), [network])
  const [from, setFrom] = useState(selection?.originId ?? '')
  const [to, setTo] = useState(selection?.destinationId ?? '')

  function choose(nextFrom: string, nextTo: string) {
    setFrom(nextFrom)
    setTo(nextTo)
    if (nextFrom && nextTo && nextFrom !== nextTo) {
      onSelect({ originId: nextFrom, destinationId: nextTo })
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-end gap-1.5">
        <div className="min-w-0 flex-1">
          <Field label="From">
            <select className={inputClass} value={from} onChange={(e) => choose(e.target.value, to)}>
              <option value="">Choose…</option>
              {stops.map((stop) => (
                <option key={stop.id} value={stop.id} disabled={stop.id === to}>
                  {stop.name}
                </option>
              ))}
            </select>
          </Field>
        </div>
        <IconButton
          icon={ArrowLeftRight}
          label="Swap origin and destination"
          className="mb-1"
          disabled={!from && !to}
          onClick={() => choose(to, from)}
        />
        <div className="min-w-0 flex-1">
          <Field label="To">
            <select className={inputClass} value={to} onChange={(e) => choose(from, e.target.value)}>
              <option value="">Choose…</option>
              {stops.map((stop) => (
                <option key={stop.id} value={stop.id} disabled={stop.id === from}>
                  {stop.name}
                </option>
              ))}
            </select>
          </Field>
        </div>
      </div>

      {state.kind === 'idle' && (
        <p className="rounded-xl border border-dashed border-line px-3 py-4 text-center text-xs text-ink-subtle">
          Pick two stops, or click a journey in the Summary table, to see its route
          before and after the change.
        </p>
      )}
      {state.kind === 'loading' && (
        <p className="flex items-center gap-2 text-sm text-ink-muted">
          <Loader2 size={16} className="animate-spin text-accent" aria-hidden />
          Finding the route…
        </p>
      )}
      {state.kind === 'error' && (
        <p role="alert" className="flex gap-2 rounded-xl bg-red-50 px-3 py-2 text-sm text-red-800">
          <TriangleAlert size={16} className="mt-0.5 shrink-0" aria-hidden />
          {state.message}
        </p>
      )}
      {state.kind === 'success' && (
        <ComparisonView network={network} comparison={state.comparison} onClear={onClear} />
      )}
    </div>
  )
}

const STATUS_CHIP: Record<JourneyComparisonStatus, { label: string; className: string }> = {
  slower: { label: 'Slower', className: 'bg-amber-50 text-amber-800' },
  faster: { label: 'Faster', className: 'bg-green-50 text-green-800' },
  impossible: { label: 'Impossible', className: 'bg-red-50 text-red-800' },
  unchanged: { label: 'No change', className: 'bg-surface-muted text-ink-muted' },
  unreachable: { label: 'Not connected', className: 'bg-surface-muted text-ink-muted' },
}

function ComparisonView({
  network,
  comparison,
  onClear,
}: {
  network: Network
  comparison: JourneyComparison
  onClear: () => void
}) {
  const stops = useMemo(() => stopsById(network), [network])
  const routes = useMemo(() => new Map(network.routes.map((r) => [r.id, r])), [network])
  const { before, after, status } = comparison
  const chip = STATUS_CHIP[status]
  const impactStatus =
    status === 'slower' || status === 'faster' || status === 'impossible' ? status : null
  const StatusIcon = impactStatus ? IMPACT_ICONS[impactStatus] : null

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-line bg-white p-3">
        <p className="flex items-center gap-1.5 text-xs font-semibold text-ink-muted">
          {stopLabel(stops, comparison.origin_id)}
          <ArrowRight size={12} aria-hidden />
          {stopLabel(stops, comparison.destination_id)}
        </p>
        <div className="mt-1 flex flex-wrap items-baseline gap-x-2 gap-y-1">
          <span className="text-lg font-semibold text-ink-subtle tabular-nums line-through decoration-1">
            {before ? formatMinutes(before.travel_time_min) : '–'}
          </span>
          <ArrowRight size={14} className="self-center text-ink-subtle" aria-hidden />
          <span className="text-xl font-semibold text-ink tabular-nums">
            {after ? formatMinutes(after.travel_time_min) : 'Not possible'}
          </span>
          <span
            className={cx(
              'ml-auto inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold',
              chip.className,
            )}
          >
            {StatusIcon && impactStatus && (
              <StatusIcon size={12} style={{ color: IMPACT_STYLES[impactStatus].color }} aria-hidden />
            )}
            {comparison.change_min !== null && status !== 'unchanged'
              ? formatChange(comparison.change_min)
              : chip.label}
          </span>
        </div>
        {comparison.reason && <p className="mt-2 text-sm text-ink-muted">{comparison.reason}</p>}
      </div>

      {after && (
        <Timeline title="After the change" plan={after} routes={routes} stops={stops} />
      )}
      {before && (
        <Timeline title="Before" plan={before} routes={routes} stops={stops} muted />
      )}

      <p className="text-[11px] leading-relaxed text-ink-subtle">
        Journey times include {(after ?? before)?.transfer_penalty_min ?? 0} min per change
        of bus. It stands in for waiting, which is not modelled.
      </p>

      <Button variant="ghost" size="sm" icon={X} onClick={onClear}>
        Clear journey
      </Button>
    </div>
  )
}

function Timeline({
  title,
  plan,
  routes,
  stops,
  muted = false,
}: {
  title: string
  plan: JourneyPlan
  routes: Map<string, Route>
  stops: Map<string, { name: string }>
  muted?: boolean
}) {
  const name = (id: string) => stops.get(id)?.name ?? id
  return (
    <section className={cx(muted && 'opacity-75')}>
      <h3 className="flex items-center justify-between gap-2 text-xs font-semibold text-ink-muted">
        {title}
        <span className="font-normal tabular-nums">{formatMinutes(plan.travel_time_min)}</span>
      </h3>
      <p className="text-[11px] text-ink-subtle tabular-nums">
        {plan.in_vehicle_min.toFixed(1)} min on the bus
        {plan.transfers > 0 &&
          ` + ${plan.transfers} ${plan.transfers === 1 ? 'change' : 'changes'} × ${plan.transfer_penalty_min} min`}
      </p>
      <ol className="mt-2">
        {plan.legs.map((leg, index) => {
          const route = routes.get(leg.route_id)
          const color = route?.color ?? '#71717a'
          const first = leg.stop_ids[0]
          const last = leg.stop_ids[leg.stop_ids.length - 1]
          const intermediate = leg.stop_ids
            .slice(1, -1)
            .filter((id) => !leg.passes_closed_stop_ids.includes(id))
          return (
            <li key={`${leg.route_id}-${index}`}>
              {index > 0 && (
                <p className="flex items-center gap-2 py-1 pl-0.5 text-[11px] text-ink-subtle">
                  <Repeat size={12} aria-hidden />
                  Change bus at {name(first)} (+{plan.transfer_penalty_min} min)
                </p>
              )}
              <div className="flex gap-3">
                <div className="flex flex-col items-center pt-1">
                  <span
                    className="h-3 w-3 rounded-full ring-2 ring-white"
                    style={{ backgroundColor: color }}
                    aria-hidden
                  />
                  <span className="w-1 flex-1 rounded-full" style={{ backgroundColor: color }} />
                  <span
                    className="h-3 w-3 rounded-full border-2 bg-white"
                    style={{ borderColor: color }}
                    aria-hidden
                  />
                </div>
                <div className="min-w-0 flex-1 pb-1 text-sm">
                  <p className="flex items-center justify-between gap-2">
                    <span className="font-medium text-ink">{name(first)}</span>
                    <span
                      className="rounded-md px-1.5 py-0.5 text-[11px] font-semibold text-white"
                      style={{ backgroundColor: color }}
                    >
                      {leg.route_id} {route?.name}
                    </span>
                  </p>
                  <p className="my-1 text-xs text-ink-subtle">
                    {leg.travel_time_min.toFixed(1)} min
                    {intermediate.length > 0 && ` · via ${intermediate.map(name).join(', ')}`}
                  </p>
                  {leg.passes_closed_stop_ids.length > 0 && (
                    <p className="mb-1 flex items-center gap-1.5 text-xs text-ink-muted">
                      <CircleSlash size={12} aria-hidden />
                      Passes {leg.passes_closed_stop_ids.map(name).join(', ')} without stopping
                    </p>
                  )}
                  <p className="font-medium text-ink">{name(last)}</p>
                </div>
              </div>
            </li>
          )
        })}
      </ol>
    </section>
  )
}
