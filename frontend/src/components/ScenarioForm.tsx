import { useMemo, useState, type FormEvent } from 'react'
import { Plus, SlidersHorizontal } from 'lucide-react'

import { currentTravelTime, neighbours, sortedStops } from '../lib/network'
import type { Network } from '../types/network'
import {
  MAX_CHANGES,
  MAX_TRAVEL_TIME_MIN,
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
  /** Current number of changes, to enforce the limit. */
  changeCount: number
  onAdd: (change: ScenarioChange) => void
  disabled: boolean
}

const CHANGE_TYPES: SegmentOption<ChangeType>[] = [
  { value: 'close_stop', label: 'Close stop', icon: CHANGE_ICONS.close_stop },
  { value: 'remove_connection', label: 'Remove link', icon: CHANGE_ICONS.remove_connection },
  { value: 'change_travel_time', label: 'Travel time', icon: CHANGE_ICONS.change_travel_time },
]

/** Builds one change at a time and hands it to the parent's list. */
export function ScenarioForm({ network, changeCount, onAdd, disabled }: ScenarioFormProps) {
  const stops = useMemo(() => sortedStops(network), [network])
  const firstStopId = stops[0]?.id ?? ''

  const [type, setType] = useState<ChangeType>('close_stop')
  const [stopId, setStopId] = useState(firstStopId)
  const [fromId, setFromId] = useState(firstStopId)
  const [toId, setToId] = useState(() => neighbours(network, firstStopId)[0]?.id ?? '')
  const [bothDirections, setBothDirections] = useState(true)
  const [travelTime, setTravelTime] = useState(() =>
    String(currentTravelTime(network, fromId, toId) ?? ''),
  )

  const toOptions = useMemo(() => neighbours(network, fromId), [network, fromId])
  const currentTime = currentTravelTime(network, fromId, toId)

  function selectLink(nextFrom: string, nextTo: string) {
    setFromId(nextFrom)
    setToId(nextTo)
    setTravelTime(String(currentTravelTime(network, nextFrom, nextTo) ?? ''))
  }

  function handleFromChange(nextFrom: string) {
    selectLink(nextFrom, neighbours(network, nextFrom)[0]?.id ?? '')
  }

  // Validate the draft change; returns the change or an error message.
  function buildChange(): ScenarioChange | string {
    if (changeCount >= MAX_CHANGES) return `A scenario can have at most ${MAX_CHANGES} changes.`
    if (type === 'close_stop') {
      if (!stopId) return 'Choose a stop.'
      return { type, stop_id: stopId }
    }
    if (!fromId || !toId) return 'Choose both stops of the connection.'
    if (type === 'remove_connection') {
      return { type, from_stop_id: fromId, to_stop_id: toId, both_directions: bothDirections }
    }
    const minutes = Number(travelTime)
    if (travelTime.trim() === '' || !Number.isFinite(minutes) || minutes <= 0) {
      return 'Travel time must be a number greater than 0.'
    }
    if (minutes > MAX_TRAVEL_TIME_MIN) {
      return `Travel time can be at most ${MAX_TRAVEL_TIME_MIN} minutes.`
    }
    return {
      type,
      from_stop_id: fromId,
      to_stop_id: toId,
      travel_time_min: minutes,
      both_directions: bothDirections,
    }
  }

  const draft = buildChange()
  const draftError = typeof draft === 'string' ? draft : null

  function handleAdd(event: FormEvent) {
    event.preventDefault()
    if (typeof draft !== 'string') onAdd(draft)
  }

  return (
    <section className="space-y-3">
      <SectionTitle icon={SlidersHorizontal}>Build a change</SectionTitle>

      <form onSubmit={handleAdd} className="space-y-3">
        <SegmentedControl
          label="Type of change"
          options={CHANGE_TYPES}
          value={type}
          onChange={setType}
          disabled={disabled}
        />

        {type === 'close_stop' ? (
          <Field label="Stop">
            <select
              className={inputClass}
              value={stopId}
              onChange={(e) => setStopId(e.target.value)}
              disabled={disabled}
            >
              {stops.map((stop) => (
                <option key={stop.id} value={stop.id}>
                  {stop.name} ({stop.id})
                </option>
              ))}
            </select>
          </Field>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-2">
              <Field label="From">
                <select
                  className={inputClass}
                  value={fromId}
                  onChange={(e) => handleFromChange(e.target.value)}
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
                  value={toId}
                  onChange={(e) => selectLink(fromId, e.target.value)}
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

            {type === 'change_travel_time' && (
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
                  value={travelTime}
                  onChange={(e) => setTravelTime(e.target.value)}
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
                checked={bothDirections}
                onChange={(e) => setBothDirections(e.target.checked)}
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
