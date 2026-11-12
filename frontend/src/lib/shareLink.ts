// Shareable links: the change list encoded in the URL's `s` query parameter.
//
//   ?s=close:CEN~remove:MKT-UNI~time:RIV-EST:9~remove:LIB-SCH:oneway
//
// Changes are separated by "~", fields by ":", the two stops of a link by "-".
// Every character used is one that browsers never percent-encode, so the link
// stays readable in the address bar. Stop ids are escaped if they contain one
// of these characters (not the case for today's ids, but possible with real
// data). Only the changes are shared, never results: the recipient's
// simulation recomputes them deterministically.

import type { Network } from '../types/network'
import { MAX_CHANGES, MAX_TRAVEL_TIME_MIN, type ScenarioChange } from '../types/scenario'

export const SHARE_PARAM = 's'
const CHANGE_SEP = '~'
const FIELD_SEP = ':'
const LINK_SEP = '-'
const ONE_WAY = 'oneway'

function encodeId(id: string): string {
  // encodeURIComponent leaves "-" and "~" alone; they are separators here.
  return encodeURIComponent(id).replace(/-/g, '%2D').replace(/~/g, '%7E')
}

function decodeId(text: string): string | null {
  try {
    const id = decodeURIComponent(text)
    return id === '' ? null : id
  } catch {
    return null // malformed escape such as "%E0%A4"
  }
}

function encodeLink(from: string, to: string, bothDirections: boolean): string {
  const link = `${encodeId(from)}${LINK_SEP}${encodeId(to)}`
  return bothDirections ? link : `${link}${FIELD_SEP}${ONE_WAY}`
}

function encodeChange(change: ScenarioChange): string {
  switch (change.type) {
    case 'close_stop':
      return `close${FIELD_SEP}${encodeId(change.stop_id)}`
    case 'remove_connection':
      return `remove${FIELD_SEP}${encodeLink(change.from_stop_id, change.to_stop_id, change.both_directions)}`
    case 'change_travel_time': {
      const link = `${encodeId(change.from_stop_id)}${LINK_SEP}${encodeId(change.to_stop_id)}`
      const oneWay = change.both_directions ? '' : `${FIELD_SEP}${ONE_WAY}`
      return `time${FIELD_SEP}${link}${FIELD_SEP}${change.travel_time_min}${oneWay}`
    }
  }
}

/** The `s` value for a change list ("" for none). */
export function encodeChanges(changes: ScenarioChange[]): string {
  return changes.map(encodeChange).join(CHANGE_SEP)
}

/** Path + query for the current page with the given changes (no `s` when empty). */
export function sharePath(pathname: string, changes: ScenarioChange[]): string {
  return changes.length === 0 ? pathname : `${pathname}?${SHARE_PARAM}=${encodeChanges(changes)}`
}

/**
 * The raw (still percent-encoded) `s` value from a query string, or null.
 * Not URLSearchParams: it would decode escaped separators inside stop ids
 * before we split on the separators.
 */
export function readShareParam(search: string): string | null {
  const prefix = `${SHARE_PARAM}=`
  const part = search
    .replace(/^\?/, '')
    .split('&')
    .find((p) => p.startsWith(prefix))
  return part === undefined ? null : part.slice(prefix.length)
}

export type DecodeResult = { ok: true; changes: ScenarioChange[] } | { ok: false; error: string }

type Parsed = ScenarioChange | string // a change or an error message

function parseLink(text: string): { from: string; to: string } | string {
  const parts = text.split(LINK_SEP)
  const from = parts.length === 2 ? decodeId(parts[0]) : null
  const to = parts.length === 2 ? decodeId(parts[1]) : null
  if (!from || !to) return `"${text}" is not a link between two stops`
  return { from, to }
}

function parseChange(text: string): Parsed {
  const [kind, ...fields] = text.split(FIELD_SEP)
  const oneWay = fields.at(-1) === ONE_WAY
  if (oneWay) fields.pop()

  if (kind === 'close') {
    const stopId = fields.length === 1 && !oneWay ? decodeId(fields[0]) : null
    return stopId ? { type: 'close_stop', stop_id: stopId } : `"${text}" is not a valid stop closure`
  }
  if (kind === 'remove') {
    if (fields.length !== 1) return `"${text}" is not a valid link removal`
    const link = parseLink(fields[0])
    if (typeof link === 'string') return link
    return {
      type: 'remove_connection',
      from_stop_id: link.from,
      to_stop_id: link.to,
      both_directions: !oneWay,
    }
  }
  if (kind === 'time') {
    if (fields.length !== 2) return `"${text}" is not a valid travel time change`
    const link = parseLink(fields[0])
    if (typeof link === 'string') return link
    // Plain decimal only: no exponents, signs, "Infinity" or hex.
    if (!/^\d+(\.\d+)?$/.test(fields[1])) return `"${fields[1]}" is not a number of minutes`
    return {
      type: 'change_travel_time',
      from_stop_id: link.from,
      to_stop_id: link.to,
      travel_time_min: Number(fields[1]),
      both_directions: !oneWay,
    }
  }
  return `"${kind}" is not a known type of change`
}

/** Same rules as the form: real stops, real links, valid times. */
function checkAgainstNetwork(change: ScenarioChange, network: Network): string | null {
  const stopIds = new Set(network.stops.map((s) => s.id))
  const unknown = (id: string) => (stopIds.has(id) ? null : `unknown stop "${id}"`)
  if (change.type === 'close_stop') return unknown(change.stop_id)

  const missing = unknown(change.from_stop_id) ?? unknown(change.to_stop_id)
  if (missing) return missing
  const connected = network.connections.some(
    (c) => c.from_stop_id === change.from_stop_id && c.to_stop_id === change.to_stop_id,
  )
  if (!connected) return `no direct link from ${change.from_stop_id} to ${change.to_stop_id}`
  if (
    change.type === 'change_travel_time' &&
    (change.travel_time_min <= 0 || change.travel_time_min > MAX_TRAVEL_TIME_MIN)
  ) {
    return `travel time must be more than 0 and at most ${MAX_TRAVEL_TIME_MIN} minutes`
  }
  return null
}

/**
 * Decode and validate a shared change list. All or nothing: one bad change
 * rejects the whole link, so a scenario is never loaded with silent gaps.
 */
export function decodeChanges(raw: string, network: Network): DecodeResult {
  if (raw === '') return { ok: true, changes: [] }
  const parts = raw.split(CHANGE_SEP)
  if (parts.length > MAX_CHANGES) {
    return { ok: false, error: `it has ${parts.length} changes (at most ${MAX_CHANGES})` }
  }
  const changes: ScenarioChange[] = []
  for (const [index, part] of parts.entries()) {
    const parsed = parseChange(part)
    const problem = typeof parsed === 'string' ? parsed : checkAgainstNetwork(parsed, network)
    if (problem !== null || typeof parsed === 'string') {
      return { ok: false, error: `change ${index + 1}: ${problem ?? parsed}` }
    }
    changes.push(parsed)
  }
  return { ok: true, changes }
}
