import { useMemo, useState, type FormEvent } from 'react'

import {
  currentTravelTime,
  describeChange,
  neighbours,
  sortedStops,
  stopsById,
} from '../lib/network'
import type { Network } from '../types/network'
import {
  MAX_CHANGES,
  MAX_TRAVEL_TIME_MIN,
  type ChangeType,
  type ScenarioChange,
} from '../types/scenario'

interface ScenarioFormProps {
  network: Network
  changes: ScenarioChange[]
  onChangesChange: (changes: ScenarioChange[]) => void
  onRun: () => void
  running: boolean
  error: string | null
}

const CHANGE_TYPE_LABELS: Record<ChangeType, string> = {
  close_stop: 'Close a stop',
  remove_connection: 'Remove a connection',
  change_travel_time: 'Change travel time',
}

const fieldClass =
  'mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm ' +
  'focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:outline-none'

export function ScenarioForm({
  network,
  changes,
  onChangesChange,
  onRun,
  running,
  error,
}: ScenarioFormProps) {
  const stops = useMemo(() => sortedStops(network), [network])
  const stopMap = useMemo(() => stopsById(network), [network])
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
    if (changes.length >= MAX_CHANGES) return `A scenario can have at most ${MAX_CHANGES} changes.`
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
    if (typeof draft !== 'string') onChangesChange([...changes, draft])
  }

  return (
    <section>
      <h2 className="text-sm font-semibold tracking-wide text-slate-500 uppercase">
        1. Build scenario
      </h2>

      <form onSubmit={handleAdd} className="mt-3 space-y-3">
        <label className="block text-sm font-medium">
          Type of change
          <select
            className={fieldClass}
            value={type}
            onChange={(e) => setType(e.target.value as ChangeType)}
          >
            {Object.entries(CHANGE_TYPE_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>

        {type === 'close_stop' ? (
          <label className="block text-sm font-medium">
            Stop
            <select className={fieldClass} value={stopId} onChange={(e) => setStopId(e.target.value)}>
              {stops.map((stop) => (
                <option key={stop.id} value={stop.id}>
                  {stop.name} ({stop.id})
                </option>
              ))}
            </select>
          </label>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-2">
              <label className="block text-sm font-medium">
                From
                <select
                  className={fieldClass}
                  value={fromId}
                  onChange={(e) => handleFromChange(e.target.value)}
                >
                  {stops.map((stop) => (
                    <option key={stop.id} value={stop.id}>
                      {stop.name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block text-sm font-medium">
                To
                <select
                  className={fieldClass}
                  value={toId}
                  onChange={(e) => selectLink(fromId, e.target.value)}
                >
                  {toOptions.map((stop) => (
                    <option key={stop.id} value={stop.id}>
                      {stop.name}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            {type === 'change_travel_time' && (
              <label className="block text-sm font-medium">
                New travel time (minutes)
                <input
                  className={fieldClass}
                  type="number"
                  min={0.1}
                  max={MAX_TRAVEL_TIME_MIN}
                  step={0.5}
                  value={travelTime}
                  onChange={(e) => setTravelTime(e.target.value)}
                />
                {currentTime !== null && (
                  <span className="mt-1 block text-xs font-normal text-slate-500">
                    Currently {currentTime} min (fastest route on this link)
                  </span>
                )}
              </label>
            )}

            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={bothDirections}
                onChange={(e) => setBothDirections(e.target.checked)}
              />
              Both directions
            </label>
          </>
        )}

        {draftError && changes.length < MAX_CHANGES && (
          <p className="text-sm text-amber-700">{draftError}</p>
        )}
        <button
          type="submit"
          disabled={draftError !== null || running}
          className="w-full rounded-md border border-blue-600 px-3 py-1.5 text-sm font-medium text-blue-700 hover:bg-blue-50 disabled:cursor-not-allowed disabled:opacity-50"
        >
          + Add change
        </button>
      </form>

      <div className="mt-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-medium">
            Changes ({changes.length}/{MAX_CHANGES})
          </h3>
          {changes.length > 0 && (
            <button
              type="button"
              onClick={() => onChangesChange([])}
              disabled={running}
              className="text-xs text-slate-500 hover:text-slate-800 disabled:opacity-50"
            >
              Clear all
            </button>
          )}
        </div>
        {changes.length === 0 ? (
          <p className="mt-1 text-sm text-slate-500">No changes yet. Add at least one.</p>
        ) : (
          <ol className="mt-2 space-y-1">
            {changes.map((change, index) => (
              <li
                key={index}
                className="flex items-center justify-between gap-2 rounded-md bg-slate-100 px-2 py-1 text-sm"
              >
                <span>
                  {index + 1}. {describeChange(change, stopMap)}
                </span>
                <button
                  type="button"
                  aria-label={`Remove change ${index + 1}`}
                  onClick={() => onChangesChange(changes.filter((_, i) => i !== index))}
                  disabled={running}
                  className="px-1 text-slate-500 hover:text-red-700 disabled:opacity-50"
                >
                  ✕
                </button>
              </li>
            ))}
          </ol>
        )}
      </div>

      <button
        type="button"
        onClick={onRun}
        disabled={changes.length === 0 || running}
        className="mt-4 w-full rounded-md bg-blue-600 px-3 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {running ? 'Simulating…' : 'Run simulation'}
      </button>
      {error && (
        <p role="alert" className="mt-2 rounded-md bg-red-50 p-2 text-sm text-red-800">
          ❌ {error}
        </p>
      )}
    </section>
  )
}
