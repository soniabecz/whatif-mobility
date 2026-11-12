import { useMemo, type FormEvent } from 'react'
import { MousePointerClick, Plus, SlidersHorizontal } from 'lucide-react'

import {
  buildChange,
  withFrom,
  withLink,
  withRoute,
  withType,
  type ChangeDraft,
} from '../lib/changeDraft'
import { currentTravelTime, neighbours, sortedStops, stopLabel, stopsById } from '../lib/network'
import type { Network } from '../types/network'
import {
  MAX_CHANGES,
  MAX_HEADWAY_MIN,
  MAX_TRAVEL_TIME_MIN,
  MIN_HEADWAY_MIN,
  type ChangeType,
  type ScenarioChange,
} from '../types/scenario'
import { CHANGE_ICONS } from './impactIcons'
import { Button } from './ui/Button'
import { Field, inputClass } from './ui/Field'
import { SectionTitle } from './ui/SectionTitle'
import { SegmentedControl, type SegmentOption } from './ui/SegmentedControl'
import { cx } from './ui/cx'

interface ScenarioFormProps {
  network: Network
  /** The change being built; owned by the parent so map clicks can edit it too. */
  draft: ChangeDraft
  onDraftChange: (draft: ChangeDraft) => void
  /** Current number of changes, to enforce the limit. */
  changeCount: number
  onAdd: (change: ScenarioChange) => void
  disabled: boolean
}

const CHANGE_TYPES: SegmentOption<ChangeType>[] = [
  { value: 'close_stop', label: 'Close stop', icon: CHANGE_ICONS.close_stop },
  { value: 'remove_connection', label: 'Remove link', icon: CHANGE_ICONS.remove_connection },
  { value: 'change_travel_time', label: 'Travel time', icon: CHANGE_ICONS.change_travel_time },
  { value: 'change_frequency', label: 'Frequency', icon: CHANGE_ICONS.change_frequency },
]

/** Builds one change at a time and hands it to the parent's list. */
export function ScenarioForm({
  network,
  draft,
  onDraftChange,
  changeCount,
  onAdd,
  disabled,
}: ScenarioFormProps) {
  const stops = useMemo(() => sortedStops(network), [network])
  const stopNames = useMemo(() => stopsById(network), [network])
  const toOptions = useMemo(() => neighbours(network, draft.fromId), [network, draft.fromId])
  const currentTime = currentTravelTime(network, draft.fromId, draft.toId)
  const routes = useMemo(
    () => [...network.routes].sort((a, b) => a.id.localeCompare(b.id)),
    [network],
  )
  const currentRoute = routes.find((route) => route.id === draft.routeId)
  const update = (patch: Partial<ChangeDraft>) => onDraftChange({ ...draft, ...patch })

  const change = buildChange(draft, changeCount)
  const draftError = typeof change === 'string' ? change : null

  function handleAdd(event: FormEvent) {
    event.preventDefault()
    if (typeof change !== 'string') onAdd(change)
  }

  return (
    <section className="space-y-3">
      <SectionTitle icon={SlidersHorizontal}>Build a change</SectionTitle>
      <p className="flex items-center gap-1.5 text-[11px] text-ink-subtle" aria-live="polite">
        <MousePointerClick size={13} className="shrink-0" aria-hidden />
        {draft.type === 'close_stop'
          ? 'Or click a stop on the map.'
          : draft.type === 'change_frequency'
            ? 'Or click a line of the route on the map.'
            : draft.awaitingTo
            ? `Now click a stop next to ${stopLabel(stopNames, draft.fromId)} on the map.`
              : 'Or click a line, or two neighbouring stops, on the map.'}
      </p>

      <form onSubmit={handleAdd} className="space-y-3">
        <SegmentedControl
          label="Type of change"
          options={CHANGE_TYPES}
          value={draft.type}
          onChange={(type) => onDraftChange(withType(draft, type))}
          disabled={disabled}
        />

        {draft.type === 'close_stop' ? (
          <Field label="Stop">
            <select
              className={inputClass}
              value={draft.stopId}
              onChange={(e) => update({ stopId: e.target.value, awaitingTo: false })}
              disabled={disabled}
            >
              {stops.map((stop) => (
                <option key={stop.id} value={stop.id}>
                  {stop.name} ({stop.id})
                </option>
              ))}
            </select>
          </Field>
        ) : draft.type === 'change_frequency' ? (
          <>
            <Field label="Route">
              <select
                className={inputClass}
                value={draft.routeId}
                onChange={(e) => onDraftChange(withRoute(network, draft, e.target.value))}
                disabled={disabled}
              >
                {routes.map((route) => (
                  <option key={route.id} value={route.id}>
                    {route.id} {route.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field
              label="A bus every (minutes)"
              hint={
                currentRoute &&
                `Currently every ${currentRoute.headway_min} min (invented timetable). Waiting is half of it on average.`
              }
            >
              <input
                className={cx(inputClass, 'tabular-nums')}
                type="number"
                min={MIN_HEADWAY_MIN}
                max={MAX_HEADWAY_MIN}
                step={0.5}
                value={draft.headway}
                onChange={(e) => update({ headway: e.target.value })}
                disabled={disabled}
              />
            </Field>
          </>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-2">
              <Field label="From">
                <select
                  className={inputClass}
                  value={draft.fromId}
                  onChange={(e) => onDraftChange(withFrom(network, draft, e.target.value))}
                  disabled={disabled}
                >
                  {stops.map((stop) => (
                    <option key={stop.id} value={stop.id}>
                      {stop.name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="To">
                <select
                  className={inputClass}
                  value={draft.toId}
                  onChange={(e) =>
                    onDraftChange(withLink(network, draft, draft.fromId, e.target.value))
                  }
                  disabled={disabled}
                >
                  {toOptions.map((stop) => (
                    <option key={stop.id} value={stop.id}>
                      {stop.name}
                    </option>
                  ))}
                </select>
              </Field>
            </div>

            {draft.type === 'change_travel_time' && (
              <Field
                label="New travel time (minutes)"
                hint={
                  currentTime !== null &&
                  `Currently ${currentTime} min (fastest route on this link)`
                }
              >
                <input
                  className={cx(inputClass, 'tabular-nums')}
                  type="number"
                  min={0.1}
                  max={MAX_TRAVEL_TIME_MIN}
                  step={0.5}
                  value={draft.travelTime}
                  onChange={(e) => update({ travelTime: e.target.value })}
                  disabled={disabled}
                />
              </Field>
            )}

            <label className="flex cursor-pointer items-center justify-between gap-3 rounded-xl bg-surface-muted px-3 py-2 text-sm text-ink">
              Both directions
              <input
                type="checkbox"
                role="switch"
                className="peer sr-only"
                checked={draft.bothDirections}
                onChange={(e) => update({ bothDirections: e.target.checked })}
                disabled={disabled}
              />
              <span
                aria-hidden
                className={cx(
                  'relative h-5 w-9 shrink-0 rounded-full bg-ink-subtle/40 transition-colors',
                  'peer-checked:bg-accent peer-focus-visible:ring-2 peer-focus-visible:ring-accent-ring',
                  'after:absolute after:top-0.5 after:left-0.5 after:h-4 after:w-4 after:rounded-full',
                  'after:bg-white after:shadow after:transition-transform peer-checked:after:translate-x-4',
                )}
              />
            </label>
          </>
        )}

        {draftError && changeCount < MAX_CHANGES && (
          <p className="text-xs text-amber-700">{draftError}</p>
        )}
        <Button
          type="submit"
          icon={Plus}
          className="w-full"
          disabled={draftError !== null || disabled}
        >
          Add to scenario
        </Button>
      </form>
    </section>
  )
}
