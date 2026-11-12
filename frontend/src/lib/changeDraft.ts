// The change being built in the scenario form. Kept outside the form so the
// map can edit it too (click a stop or a line). Pure functions: no React.

import type { Network } from '../types/network'
import {
  MAX_CHANGES,
  MAX_HEADWAY_MIN,
  MAX_TRAVEL_TIME_MIN,
  MIN_HEADWAY_MIN,
  type AddStop,
  type ChangeType,
  type ScenarioChange,
} from '../types/scenario'
import {
  addedConnectionProblem,
  addedStopProblem,
  currentTravelTime,
  linkKey,
  neighbours,
  sortedStops,
} from './network'

export interface ChangeDraft {
  type: ChangeType
  /** Stop for "close stop". */
  stopId: string
  /** Link for "remove link" / "travel time". */
  fromId: string
  toId: string
  /** Text of the travel time input (validated in buildChange). */
  travelTime: string
  bothDirections: boolean
  /** True after a map click set From: the next click on a neighbour sets To. */
  awaitingTo: boolean
  /** Route and text of the headway input for "frequency". */
  routeId: string
  headway: string
  /** "Add stop": where it goes, its name, and the time from the new stop on to To
      (travelTime is the time From -> new stop). */
  position: { lat: number; lon: number } | null
  stopName: string
  secondTime: string
}

function timeText(network: Network, fromId: string, toId: string): string {
  return String(currentTravelTime(network, fromId, toId) ?? '')
}

function headwayText(network: Network, routeId: string): string {
  return String(network.routes.find((route) => route.id === routeId)?.headway_min ?? '')
}

export function initialDraft(network: Network): ChangeDraft {
  const first = sortedStops(network)[0]?.id ?? ''
  const to = neighbours(network, first)[0]?.id ?? ''
  const route = [...network.routes].sort((a, b) => a.id.localeCompare(b.id))[0]?.id ?? ''
  return {
    type: 'close_stop',
    stopId: first,
    fromId: first,
    toId: to,
    travelTime: timeText(network, first, to),
    bothDirections: true,
    awaitingTo: false,
    routeId: route,
    headway: headwayText(network, route),
    position: null,
    stopName: '',
    secondTime: '',
  }
}

/** A route was chosen: fill in its current headway. */
export function withRoute(network: Network, draft: ChangeDraft, routeId: string): ChangeDraft {
  return { ...draft, routeId, headway: headwayText(network, routeId), awaitingTo: false }
}

export function withType(draft: ChangeDraft, type: ChangeType): ChangeDraft {
  // New links and stops have no current time: the user always enters it (never pre-filled).
  const fresh = type === 'add_connection' || type === 'add_stop'
  const travelTime = fresh ? '' : draft.travelTime
  return { ...draft, type, travelTime, secondTime: fresh ? '' : draft.secondTime, awaitingTo: false }
}

/** Direct links of a route, once per street (in the direction first listed). */
export function routeLinks(network: Network, routeId: string): { fromId: string; toId: string }[] {
  const seen = new Set<string>()
  const links: { fromId: string; toId: string }[] = []
  for (const c of network.connections) {
    const key = linkKey(c.from_stop_id, c.to_stop_id)
    if (c.route_id !== routeId || seen.has(key)) continue
    seen.add(key)
    links.push({ fromId: c.from_stop_id, toId: c.to_stop_id })
  }
  return links
}

/** "Add stop": a route was chosen; the new stop goes on its first link until changed. */
export function withStopRoute(network: Network, draft: ChangeDraft, routeId: string): ChangeDraft {
  const first = routeLinks(network, routeId)[0]
  return { ...draft, routeId, fromId: first?.fromId ?? '', toId: first?.toId ?? '' }
}

/** "Add stop": the map was clicked at an empty spot. */
export function placeStop(draft: ChangeDraft, lat: number, lon: number): ChangeDraft {
  // 6 decimals = about 0.1 m: plenty, and keeps shared links short.
  const round = (value: number) => Math.round(value * 1e6) / 1e6
  return { ...draft, position: { lat: round(lat), lon: round(lon) } }
}

/** First free id N1, N2, ... (the network passed includes stops added earlier). */
export function nextStopId(network: Network): string {
  const used = new Set(network.stops.map((stop) => stop.id))
  let n = 1
  while (used.has(`N${n}`)) n += 1
  return `N${n}`
}

/** A link was chosen: fill in its current travel time. */
export function withLink(
  network: Network,
  draft: ChangeDraft,
  fromId: string,
  toId: string,
): ChangeDraft {
  return { ...draft, fromId, toId, travelTime: timeText(network, fromId, toId), awaitingTo: false }
}

/** From changed (dropdown): To becomes its first neighbour. */
export function withFrom(network: Network, draft: ChangeDraft, fromId: string): ChangeDraft {
  return withLink(network, draft, fromId, neighbours(network, fromId)[0]?.id ?? '')
}

/**
 * A stop was clicked on the map.
 * - "Close stop": it becomes the stop.
 * - Link types: it becomes From, unless From was just picked and this is one
 *   of its neighbours; then it becomes To.
 */
export function clickStop(network: Network, draft: ChangeDraft, stopId: string): ChangeDraft {
  // A stop can belong to several routes: on "frequency" only lines select a route.
  // "Add stop" places a NEW stop, so an existing one is not a target.
  if (draft.type === 'change_frequency' || draft.type === 'add_stop') return draft
  // "Add link": any two different stops (they are not linked yet), From then To.
  if (draft.type === 'add_connection') {
    if (draft.awaitingTo && stopId !== draft.fromId) return { ...draft, toId: stopId, awaitingTo: false }
    return { ...draft, fromId: stopId, awaitingTo: true }
  }
  if (draft.type === 'close_stop') return { ...draft, stopId, awaitingTo: false }
  const isNeighbour = neighbours(network, draft.fromId).some((stop) => stop.id === stopId)
  if (draft.awaitingTo && isNeighbour) return withLink(network, draft, draft.fromId, stopId)
  return { ...withFrom(network, draft, stopId), awaitingTo: true }
}

/**
 * A line (one route's segment) was clicked on the map. "Frequency" selects
 * its route; otherwise it selects the link ("close stop" switches to "remove link").
 */
export function clickLink(
  network: Network,
  draft: ChangeDraft,
  fromId: string,
  toId: string,
  routeId: string,
): ChangeDraft {
  if (draft.type === 'change_frequency') return withRoute(network, draft, routeId)
  // "Add link": a line picks the route that gets the new link.
  if (draft.type === 'add_connection') return { ...draft, routeId, awaitingTo: false }
  // "Add stop": a line picks the route and the link the new stop goes on.
  if (draft.type === 'add_stop') {
    const link = routeLinks(network, routeId).find(
      (l) => linkKey(l.fromId, l.toId) === linkKey(fromId, toId),
    )
    return link ? { ...draft, routeId, fromId: link.fromId, toId: link.toId } : draft
  }
  const type = draft.type === 'close_stop' ? 'remove_connection' : draft.type
  return withLink(network, { ...draft, type }, fromId, toId)
}

/** What the map highlights as "currently selected in the form". */
export interface DraftSelection {
  stopIds: string[]
  /** linkKey of the selected street, if a link type is chosen. */
  link: string | null
  /** The whole route, for "frequency". */
  routeId: string | null
  /** "Add link": the planned new link (not a street yet), drawn as a preview. */
  newLink: { fromId: string; toId: string } | null
  /** "Add stop": where the new stop will be placed. */
  newStop: { lat: number; lon: number } | null
}

export function draftSelection(draft: ChangeDraft): DraftSelection {
  const none = { stopIds: [], link: null, routeId: null, newLink: null, newStop: null }
  if (draft.type === 'change_frequency') return { ...none, routeId: draft.routeId || null }
  if (draft.type === 'close_stop') return { ...none, stopIds: draft.stopId ? [draft.stopId] : [] }
  const stopIds = [draft.fromId, draft.toId].filter((id) => id !== '')
  const both = draft.fromId !== '' && draft.toId !== '' && draft.fromId !== draft.toId
  if (draft.type === 'add_connection') {
    return { ...none, stopIds, newLink: both ? { fromId: draft.fromId, toId: draft.toId } : null }
  }
  if (draft.type === 'add_stop') {
    return {
      ...none,
      stopIds,
      link: both ? linkKey(draft.fromId, draft.toId) : null,
      newStop: draft.position,
    }
  }
  return { ...none, stopIds, link: both ? linkKey(draft.fromId, draft.toId) : null }
}

/** Validate the draft; returns the change or an error message for the user. */
export function buildChange(
  draft: ChangeDraft,
  changeCount: number,
  network: Network,
): ScenarioChange | string {
  if (changeCount >= MAX_CHANGES) return `A scenario can have at most ${MAX_CHANGES} changes.`
  if (draft.type === 'close_stop') {
    if (!draft.stopId) return 'Choose a stop.'
    return { type: 'close_stop', stop_id: draft.stopId }
  }
  if (draft.type === 'change_frequency') {
    if (!draft.routeId) return 'Choose a route.'
    const minutes = Number(draft.headway)
    if (
      draft.headway.trim() === '' ||
      !Number.isFinite(minutes) ||
      minutes < MIN_HEADWAY_MIN ||
      minutes > MAX_HEADWAY_MIN
    ) {
      return `A bus can run every ${MIN_HEADWAY_MIN} to ${MAX_HEADWAY_MIN} minutes.`
    }
    return { type: 'change_frequency', route_id: draft.routeId, headway_min: minutes }
  }
  if (draft.type === 'add_stop') {
    if (!draft.position) return 'Click the map to place the new stop.'
    if (!draft.stopName.trim()) return 'Give the new stop a name.'
    if (!draft.routeId || !draft.fromId || !draft.toId) return 'Choose the route and the link.'
    const first = travelMinutes(draft.travelTime)
    if (typeof first === 'string') return first
    const second = travelMinutes(draft.secondTime)
    if (typeof second === 'string') return second
    const change: AddStop = {
      type: 'add_stop',
      stop_id: nextStopId(network),
      name: draft.stopName.trim(),
      lat: draft.position.lat,
      lon: draft.position.lon,
      route_id: draft.routeId,
      from_stop_id: draft.fromId,
      to_stop_id: draft.toId,
      time_from_min: first,
      time_to_min: second,
    }
    const problem = addedStopProblem(network, change)
    return problem ? `Not possible: ${problem}.` : change
  }
  if (draft.type === 'add_connection') {
    if (!draft.routeId) return 'Choose a route.'
    if (!draft.fromId || !draft.toId) return 'Choose both stops of the new link.'
    const problem = addedConnectionProblem(
      network,
      draft.routeId,
      draft.fromId,
      draft.toId,
      draft.bothDirections,
    )
    if (problem) return `Not possible: ${problem}.`
    const time = travelMinutes(draft.travelTime)
    if (typeof time === 'string') return time
    return {
      type: 'add_connection',
      route_id: draft.routeId,
      from_stop_id: draft.fromId,
      to_stop_id: draft.toId,
      travel_time_min: time,
      both_directions: draft.bothDirections,
    }
  }
  if (!draft.fromId || !draft.toId) return 'Choose both stops of the connection.'
  if (draft.type === 'remove_connection') {
    return {
      type: 'remove_connection',
      from_stop_id: draft.fromId,
      to_stop_id: draft.toId,
      both_directions: draft.bothDirections,
    }
  }
  const minutes = travelMinutes(draft.travelTime)
  if (typeof minutes === 'string') return minutes
  return {
    type: 'change_travel_time',
    from_stop_id: draft.fromId,
    to_stop_id: draft.toId,
    travel_time_min: minutes,
    both_directions: draft.bothDirections,
  }
}

/** The travel time input as minutes, or an error message. */
function travelMinutes(text: string): number | string {
  const minutes = Number(text)
  if (text.trim() === '' || !Number.isFinite(minutes) || minutes <= 0) {
    return 'Travel time must be a number greater than 0.'
  }
  if (minutes > MAX_TRAVEL_TIME_MIN) return `Travel time can be at most ${MAX_TRAVEL_TIME_MIN} minutes.`
  return minutes
}
