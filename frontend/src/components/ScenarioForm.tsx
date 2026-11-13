import { useMemo, type FormEvent } from 'react'
import { MapPin, MousePointerClick, Plus, SlidersHorizontal } from 'lucide-react'

import {
  EMPTY_ROUTE,
  buildChange,
  withFrom,
  nextStopId,
  routeLinks,
  withLink,
  withRoute,
  withStopRoute,
  withType,
  type ChangeDraft,
} from '../lib/changeDraft'
import {
  currentTravelTime,
  neighbours,
  sortedStops,
  stopLabel,
  stopsById,
  straightLineKm,
} from '../lib/network'
import type { Network } from '../types/network'
import {
  MAX_CHANGES,
  MAX_HEADWAY_MIN,
  MAX_TRAVEL_TIME_MIN,
  MIN_HEADWAY_MIN,
  type ChangeType,
  type ScenarioChange,
} from '../types/scenario'
import { AddRouteFields } from './AddRouteFields'
import { CHANGE_ICONS } from './impactIcons'
import { Button } from './ui/Button'
import { Field, inputClass } from './ui/Field'
import { SectionTitle } from './ui/SectionTitle'
import { SegmentedControl, type SegmentOption } from './ui/SegmentedControl'
import { Switch } from './ui/Switch'
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
  { value: 'add_connection', label: 'Add link', icon: CHANGE_ICONS.add_connection },
  { value: 'add_stop', label: 'Add stop', icon: CHANGE_ICONS.add_stop },
  { value: 'add_route', label: 'Add route', icon: CHANGE_ICONS.add_route },
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
  const links = useMemo(() => routeLinks(network, draft.routeId), [network, draft.routeId])
  const routeTime =
    network.connections.find(
      (c) =>
        c.route_id === draft.routeId && c.from_stop_id === draft.fromId && c.to_stop_id === draft.toId,
    )?.travel_time_min ?? null
  const distanceKm =
    draft.type === 'add_connection' ? straightLineKm(network, draft.fromId, draft.toId) : null
  const update = (patch: Partial<ChangeDraft>) => onDraftChange({ ...draft, ...patch })

  const change = buildChange(draft, changeCount, network)
  const draftError = typeof change === 'string' ? change : null

  function handleAdd(event: FormEvent) {
    event.preventDefault()
    if (typeof change === 'string') return
    onAdd(change)
    // A route is added once: start the next one empty (its colour picks the next free one).
    if (change.type === 'add_route') onDraftChange({ ...draft, route: EMPTY_ROUTE })
  }

  return (
    <section className="space-y-3">
      <SectionTitle icon={SlidersHorizontal}>Build a change</SectionTitle>
      <p className="flex items-center gap-1.5 text-[11px] text-ink-subtle" aria-live="polite">
        <MousePointerClick size={13} className="shrink-0" aria-hidden />
        {draft.type === 'add_route'
          ? draft.route.stopIds.length === 0
            ? 'Click the stops on the map in the order the bus calls.'
            : draft.route.stopIds.length >= 3 && !draft.route.isLoop
              ? 'Click the next stop, or the first one again to make a loop.'
              : 'Click the next stop on the map.'
          : draft.type === 'add_stop'
          ? draft.position
            ? 'Click the map again to move it, or a line to choose the route and link.'
            : 'Click the map where the new stop should be.'
          : draft.type === 'close_stop'
          ? 'Or click a stop on the map.'
          : draft.type === 'change_frequency'
            ? 'Or click a line of the route on the map.'
            : draft.type === 'add_connection' && !draft.awaitingTo
              ? 'Or click two stops (and a line for the route) on the map.'
              : draft.awaitingTo
            ? draft.type === 'add_connection'
              ? `Now click the other stop of the new link from ${stopLabel(stopNames, draft.fromId)}.`
              : `Now click a stop next to ${stopLabel(stopNames, draft.fromId)} on the map.`
                : 'Or click a line, or two neighbouring stops, on the map.'}
      </p>

      <form onSubmit={handleAdd} className="space-y-3">
        <SegmentedControl
          label="Type of change"
          options={CHANGE_TYPES}
          value={draft.type}
          onChange={(type) => {
            const next = withType(draft, type)
            // "Add stop" needs a real link of the route: start on its first one.
            onDraftChange(type === 'add_stop' ? withStopRoute(network, next, next.routeId) : next)
          }}
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
                step="any"
                value={draft.headway}
                onChange={(e) => update({ headway: e.target.value })}
                disabled={disabled}
              />
            </Field>
          </>
        ) : draft.type === 'add_route' ? (
          <AddRouteFields
            network={network}
            draft={draft}
            onDraftChange={onDraftChange}
            disabled={disabled}
          />
        ) : draft.type === 'add_stop' ? (
          <>
            <p className="flex items-center gap-2 rounded-xl bg-surface-muted px-3 py-2 text-xs text-ink-muted">
              <MapPin size={14} className="shrink-0 text-accent" aria-hidden />
              {draft.position
                ? `Placed at ${draft.position.lat.toFixed(5)}, ${draft.position.lon.toFixed(5)}`
                : 'Not placed yet: click the map.'}
            </p>
            <Field label="Name of the new stop" hint={`Id ${nextStopId(network)} (automatic)`}>
              <input
                className={inputClass}
                maxLength={100}
                placeholder="e.g. Old Market"
                value={draft.stopName}
                onChange={(e) => update({ stopName: e.target.value })}
                disabled={disabled}
              />
            </Field>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Route">
                <select
                  className={inputClass}
                  value={draft.routeId}
                  onChange={(e) => onDraftChange(withStopRoute(network, draft, e.target.value))}
                  disabled={disabled}
                >
                  {routes.map((route) => (
                    <option key={route.id} value={route.id}>
                      {route.id} {route.name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Between">
                <select
                  className={inputClass}
                  value={`${draft.fromId}|${draft.toId}`}
                  onChange={(e) => {
                    const [fromId, toId] = e.target.value.split('|')
                    update({ fromId, toId })
                  }}
                  disabled={disabled}
                >
                  {links.map((link) => (
                    <option key={`${link.fromId}|${link.toId}`} value={`${link.fromId}|${link.toId}`}>
                      {stopLabel(stopNames, link.fromId)} – {stopLabel(stopNames, link.toId)}
                    </option>
                  ))}
                </select>
              </Field>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <Field label={`Minutes from ${stopLabel(stopNames, draft.fromId)}`}>
                <input
                  className={cx(inputClass, 'tabular-nums')}
                  type="number"
                  min={0.1}
                  max={MAX_TRAVEL_TIME_MIN}
                  step="any"
                  value={draft.travelTime}
                  onChange={(e) => update({ travelTime: e.target.value })}
                  disabled={disabled}
                />
              </Field>
              <Field label={`Minutes on to ${stopLabel(stopNames, draft.toId)}`}>
                <input
                  className={cx(inputClass, 'tabular-nums')}
                  type="number"
                  min={0.1}
                  max={MAX_TRAVEL_TIME_MIN}
                  step="any"
                  value={draft.secondTime}
                  onChange={(e) => update({ secondTime: e.target.value })}
                  disabled={disabled}
                />
              </Field>
            </div>
            {routeTime !== null && (
              <p className="text-[11px] text-ink-subtle">
                {draft.routeId} takes {routeTime} min from {stopLabel(stopNames, draft.fromId)} to{' '}
                {stopLabel(stopNames, draft.toId)} today.
              </p>
            )}
          </>
        ) : draft.type === 'add_connection' ? (
          <>
            <Field label="Route that gets the new link">
              <select
                className={inputClass}
                value={draft.routeId}
                onChange={(e) => update({ routeId: e.target.value, awaitingTo: false })}
                disabled={disabled}
              >
                {routes.map((route) => (
                  <option key={route.id} value={route.id}>
                    {route.id} {route.name}
                  </option>
                ))}
              </select>
            </Field>
            <div className="grid grid-cols-2 gap-2">
              {(['fromId', 'toId'] as const).map((key) => (
                <Field key={key} label={key === 'fromId' ? 'From' : 'To'}>
                  <select
                    className={inputClass}
                    value={draft[key]}
                    onChange={(e) => update({ [key]: e.target.value, awaitingTo: false })}
                    disabled={disabled}
                  >
                    {stops.map((stop) => (
                      <option key={stop.id} value={stop.id}>
                        {stop.name}
                      </option>
                    ))}
                  </select>
                </Field>
              ))}
            </div>
            <Field
              label="Travel time (minutes)"
              hint={
                distanceKm !== null &&
                `The stops are ${distanceKm.toFixed(1)} km apart in a straight line.`
              }
            >
              <input
                className={cx(inputClass, 'tabular-nums')}
                type="number"
                min={0.1}
                max={MAX_TRAVEL_TIME_MIN}
                step="any"
                placeholder="e.g. 5"
                value={draft.travelTime}
                onChange={(e) => update({ travelTime: e.target.value })}
                disabled={disabled}
              />
            </Field>
            <BothDirections
              checked={draft.bothDirections}
              onChange={(bothDirections) => update({ bothDirections })}
              disabled={disabled}
            />
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
                  step="any"
                  value={draft.travelTime}
                  onChange={(e) => update({ travelTime: e.target.value })}
                  disabled={disabled}
                />
              </Field>
            )}

            <BothDirections
              checked={draft.bothDirections}
              onChange={(bothDirections) => update({ bothDirections })}
              disabled={disabled}
            />
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

function BothDirections({
  checked,
  onChange,
  disabled,
}: {
  checked: boolean
  onChange: (checked: boolean) => void
  disabled: boolean
}) {
  return <Switch label="Both directions" checked={checked} onChange={onChange} disabled={disabled} />
}
