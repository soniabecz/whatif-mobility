// "Add route" tab of the scenario form: name, colour, headway and the stops in
// order (clicked on the map or chosen here), with a travel time per stretch.

import { useMemo } from 'react'
import { ArrowDown, RotateCcw, Undo2 } from 'lucide-react'

import {
  appendRouteStop,
  nextRouteId,
  removeLastRouteStop,
  routeColor,
  withRouteDraft,
  type ChangeDraft,
} from '../lib/changeDraft'
import { sortedStops, stopLabel, stopsById, straightLineKm } from '../lib/network'
import type { Network } from '../types/network'
import {
  MAX_HEADWAY_MIN,
  MAX_ROUTE_STOPS,
  MAX_TRAVEL_TIME_MIN,
  MIN_HEADWAY_MIN,
  NEW_ROUTE_COLORS,
} from '../types/scenario'
import { Button } from './ui/Button'
import { Field, inputBaseClass, inputClass } from './ui/Field'
import { Switch } from './ui/Switch'
import { cx } from './ui/cx'

const COLOR_NAMES: Record<(typeof NEW_ROUTE_COLORS)[number], string> = {
  '#7c3aed': 'Violet',
  '#db2777': 'Pink',
  '#0d9488': 'Teal',
  '#92400e': 'Brown',
  '#ca8a04': 'Gold',
  '#475569': 'Slate',
}

interface AddRouteFieldsProps {
  network: Network
  draft: ChangeDraft
  onDraftChange: (draft: ChangeDraft) => void
  disabled: boolean
}

export function AddRouteFields({ network, draft, onDraftChange, disabled }: AddRouteFieldsProps) {
  const { route } = draft
  const stopNames = useMemo(() => stopsById(network), [network])
  const name = (id: string) => stopLabel(stopNames, id)
  const color = routeColor(network, draft)
  const usedColors = new Set(network.routes.map((r) => r.color.toLowerCase()))
  const available = sortedStops(network).filter((stop) => !route.stopIds.includes(stop.id))
  const update = (patch: Partial<ChangeDraft['route']>) => onDraftChange(withRouteDraft(draft, patch))
  const first = route.stopIds[0]
  const last = route.stopIds.at(-1)

  return (
    <>
      <Field label="Name of the new route" hint={`Id ${nextRouteId(network)} (automatic)`}>
        <input
          className={inputClass}
          maxLength={100}
          placeholder="e.g. Cross Town"
          value={route.name}
          onChange={(e) => update({ name: e.target.value })}
          disabled={disabled}
        />
      </Field>

      <div className="grid grid-cols-2 gap-2">
        <fieldset>
          <legend className="text-xs font-semibold text-ink-muted">Colour</legend>
          <div role="radiogroup" aria-label="Colour" className="mt-1 flex h-10 flex-wrap items-center gap-1.5">
            {NEW_ROUTE_COLORS.map((option) => {
              const used = usedColors.has(option)
              const selected = option === color
              return (
                <button
                  key={option}
                  type="button"
                  role="radio"
                  aria-checked={selected}
                  aria-label={`${COLOR_NAMES[option]}${used ? ' (used by another route)' : ''}`}
                  title={COLOR_NAMES[option]}
                  onClick={() => update({ color: option })}
                  disabled={disabled || used}
                  className={cx(
                    'h-5 w-5 rounded-full ring-offset-2 transition',
                    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-ring',
                    selected ? 'ring-2 ring-ink' : 'hover:scale-110',
                    used && 'cursor-not-allowed opacity-25',
                  )}
                  style={{ backgroundColor: option }}
                />
              )
            })}
          </div>
        </fieldset>
        <Field label="A bus every (minutes)">
          <input
            className={cx(inputClass, 'tabular-nums')}
            type="number"
            min={MIN_HEADWAY_MIN}
            max={MAX_HEADWAY_MIN}
            step="any"
            placeholder="e.g. 10"
            value={route.headway}
            onChange={(e) => update({ headway: e.target.value })}
            disabled={disabled}
          />
        </Field>
      </div>

      <div>
        <p className="text-xs font-semibold text-ink-muted">
          Stops in order{' '}
          <span className="font-normal text-ink-subtle">
            ({route.stopIds.length} of at most {MAX_ROUTE_STOPS})
          </span>
        </p>
        {route.stopIds.length === 0 ? (
          <p className="mt-1 rounded-xl bg-surface-muted px-3 py-2 text-xs text-ink-muted">
            No stops yet: click them on the map, or choose them below.
          </p>
        ) : (
          <ol className="mt-1 space-y-1" aria-label="Stops of the new route">
            {route.stopIds.map((stopId, index) => (
              <li key={stopId}>
                <StopRow index={index + 1} name={name(stopId)} color={color} />
                {index < route.stopIds.length - 1 && (
                  <TimeRow
                    label={`Minutes from ${name(stopId)} to ${name(route.stopIds[index + 1])}`}
                    value={route.times[index] ?? ''}
                    km={straightLineKm(network, stopId, route.stopIds[index + 1])}
                    onChange={(value) =>
                      update({ times: route.times.map((t, i) => (i === index ? value : t)) })
                    }
                    disabled={disabled}
                  />
                )}
              </li>
            ))}
            {route.isLoop && first && last && (
              <li>
                <TimeRow
                  label={`Minutes from ${name(last)} back to ${name(first)}`}
                  value={route.loopTime}
                  km={straightLineKm(network, last, first)}
                  onChange={(loopTime) => update({ loopTime })}
                  disabled={disabled}
                  loop
                />
                <StopRow index={1} name={`${name(first)} (back to the start)`} color={color} />
              </li>
            )}
          </ol>
        )}
        <div className="mt-2 flex gap-2">
          <label className="min-w-0 flex-1">
            <span className="sr-only">Add a stop to the route</span>
            <select
              className={cx(inputBaseClass, 'h-10 w-full')}
              value=""
              onChange={(e) => e.target.value && onDraftChange(appendRouteStop(draft, e.target.value))}
              disabled={disabled || route.stopIds.length >= MAX_ROUTE_STOPS}
            >
              <option value="">Add a stop…</option>
              {available.map((stop) => (
                <option key={stop.id} value={stop.id}>
                  {stop.name}
                </option>
              ))}
            </select>
          </label>
          <Button
            icon={Undo2}
            onClick={() => onDraftChange(removeLastRouteStop(draft))}
            disabled={disabled || route.stopIds.length === 0}
          >
            Remove last
          </Button>
        </div>
      </div>

      <Switch
        label="Loop (back to the first stop)"
        checked={route.isLoop}
        onChange={(isLoop) => update({ isLoop })}
        disabled={disabled || route.stopIds.length < 3}
      />
      <Switch
        label="Both directions"
        checked={draft.bothDirections}
        onChange={(bothDirections) => onDraftChange({ ...draft, bothDirections })}
        disabled={disabled}
      />
    </>
  )
}

function StopRow({ index, name, color }: { index: number; name: string; color: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-ink">
      <span
        className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border-[3px] bg-white text-[10px] font-semibold tabular-nums"
        style={{ borderColor: color }}
      >
        {index}
      </span>
      {name}
    </div>
  )
}

function TimeRow({
  label,
  value,
  km,
  onChange,
  disabled,
  loop = false,
}: {
  label: string
  value: string
  km: number | null
  onChange: (value: string) => void
  disabled: boolean
  loop?: boolean
}) {
  const Icon = loop ? RotateCcw : ArrowDown
  return (
    <div className="my-1 ml-2 flex items-center gap-2 border-l-2 border-dashed border-line pl-4 text-[11px] text-ink-subtle">
      <Icon size={12} className="shrink-0" aria-hidden />
      <input
        aria-label={label}
        className={cx(inputBaseClass, 'h-8 w-20 shrink-0 tabular-nums')}
        type="number"
        min={0.1}
        max={MAX_TRAVEL_TIME_MIN}
        step="any"
        placeholder="min"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
      />
      min{km !== null && <span>· {km.toFixed(1)} km straight line</span>}
    </div>
  )
}
