// Pure helpers over the network data. No React, no API calls.

import type { Network, Stop } from '../types/network'
import type { AddStop, ScenarioChange } from '../types/scenario'

/** Order-independent key for the street between two stops. */
export function linkKey(a: string, b: string): string {
  return a < b ? `${a}|${b}` : `${b}|${a}`
}

export function stopsById(network: Network): Map<string, Stop> {
  return new Map(network.stops.map((stop) => [stop.id, stop]))
}

export function stopLabel(stops: Map<string, Stop>, stopId: string): string {
  return stops.get(stopId)?.name ?? stopId
}

export function sortedStops(network: Network): Stop[] {
  return [...network.stops].sort((a, b) => a.name.localeCompare(b.name))
}

/** Stops directly reachable from `stopId` by one connection, sorted by name. */
export function neighbours(network: Network, stopId: string): Stop[] {
  const ids = new Set(
    network.connections.filter((c) => c.from_stop_id === stopId).map((c) => c.to_stop_id),
  )
  return sortedStops(network).filter((stop) => ids.has(stop.id))
}

/**
 * Current travel time from -> to. When several routes serve the link this
 * is the fastest, matching the backend graph's edge weight.
 */
export function currentTravelTime(
  network: Network,
  fromId: string,
  toId: string,
): number | null {
  const times = network.connections
    .filter((c) => c.from_stop_id === fromId && c.to_stop_id === toId)
    .map((c) => c.travel_time_min)
  return times.length > 0 ? Math.min(...times) : null
}

/** One line to draw per route per street (A->B and B->A share a line). */
export interface Segment {
  key: string
  routeId: string
  from: Stop
  to: Stop
  travelTimeMin: number
}

export function routeSegments(network: Network): Segment[] {
  const stops = stopsById(network)
  const seen = new Set<string>()
  const segments: Segment[] = []
  for (const c of network.connections) {
    const key = `${c.route_id}:${linkKey(c.from_stop_id, c.to_stop_id)}`
    const from = stops.get(c.from_stop_id)
    const to = stops.get(c.to_stop_id)
    if (seen.has(key) || !from || !to) continue
    seen.add(key)
    segments.push({ key, routeId: c.route_id, from, to, travelTimeMin: c.travel_time_min })
  }
  return segments
}

/** Streets and stops touched by the scenario, for highlighting on the map. */
export interface ScenarioHighlights {
  closedStopIds: Set<string>
  removedLinks: Set<string>
  retimedLinks: Set<string>
  /** New headway per route (the last change to a route wins, as in the backend). */
  headways: Map<string, number>
  /** Links added to a route, drawn as dashed lines in the route's colour. */
  addedLinks: AddedLink[]
  /** Stops added by the scenario (drawn with their own marker). */
  addedStops: AddStop[]
}

export interface AddedLink {
  routeId: string
  fromId: string
  toId: string
  travelTimeMin: number
  bothDirections: boolean
}

export function scenarioHighlights(changes: ScenarioChange[]): ScenarioHighlights {
  const highlights: ScenarioHighlights = {
    closedStopIds: new Set(),
    removedLinks: new Set(),
    retimedLinks: new Set(),
    headways: new Map(),
    addedLinks: [],
    addedStops: [],
  }
  for (const change of changes) {
    switch (change.type) {
      case 'close_stop':
        highlights.closedStopIds.add(change.stop_id)
        break
      case 'remove_connection':
        highlights.removedLinks.add(linkKey(change.from_stop_id, change.to_stop_id))
        break
      case 'change_travel_time':
        highlights.retimedLinks.add(linkKey(change.from_stop_id, change.to_stop_id))
        break
      case 'change_frequency':
        highlights.headways.set(change.route_id, change.headway_min)
        break
      case 'add_connection':
        highlights.addedLinks.push({
          routeId: change.route_id,
          fromId: change.from_stop_id,
          toId: change.to_stop_id,
          travelTimeMin: change.travel_time_min,
          bothDirections: change.both_directions,
        })
        break
      case 'add_stop':
        highlights.addedStops.push(change)
        break
    }
  }
  return highlights
}

export function describeChange(change: ScenarioChange, stops: Map<string, Stop>): string {
  const name = (id: string) => stopLabel(stops, id)
  switch (change.type) {
    case 'close_stop':
      return `Close ${name(change.stop_id)}`
    case 'remove_connection':
      return `Remove ${name(change.from_stop_id)} ${arrow(change.both_directions)} ${name(change.to_stop_id)}`
    case 'change_travel_time':
      return `${name(change.from_stop_id)} ${arrow(change.both_directions)} ${name(change.to_stop_id)}: ${change.travel_time_min} min`
    case 'change_frequency':
      return `${change.route_id}: a bus every ${change.headway_min} min`
    case 'add_connection':
      return `Add ${change.route_id}: ${name(change.from_stop_id)} ${arrow(change.both_directions)} ${name(change.to_stop_id)}, ${change.travel_time_min} min`
    case 'add_stop':
      return `New stop ${change.name} on ${change.route_id}: ${name(change.from_stop_id)} ${change.time_from_min} min → ${change.time_to_min} min ${name(change.to_stop_id)}`
  }
}

function arrow(bothDirections: boolean): string {
  return bothDirections ? '↔' : '→'
}

/**
 * Why a route cannot get a new link a -> b (null if it can). Same rules as the
 * backend: two different stops, at least one already on the route, and the
 * route does not already run between them (in a requested direction).
 */
export function addedConnectionProblem(
  network: Network,
  routeId: string,
  fromId: string,
  toId: string,
  bothDirections: boolean,
): string | null {
  if (fromId === toId) return 'a connection needs two different stops'
  const onRoute = network.connections.filter((c) => c.route_id === routeId)
  const served = new Set(onRoute.flatMap((c) => [c.from_stop_id, c.to_stop_id]))
  if (!served.has(fromId) && !served.has(toId)) {
    return `route ${routeId} stops at neither ${fromId} nor ${toId}`
  }
  const directions = bothDirections ? [[fromId, toId], [toId, fromId]] : [[fromId, toId]]
  for (const [a, b] of directions) {
    if (onRoute.some((c) => c.from_stop_id === a && c.to_stop_id === b)) {
      return `route ${routeId} already runs from ${a} to ${b}`
    }
  }
  return null
}

/** Straight-line distance between two stops in km (null if either is unknown or the same). */
export function straightLineKm(network: Network, a: string, b: string): number | null {
  const stops = stopsById(network)
  const from = stops.get(a)
  const to = stops.get(b)
  if (!from || !to || a === b) return null
  const rad = (deg: number) => (deg * Math.PI) / 180
  const dLat = rad(to.lat - from.lat)
  const dLon = rad(to.lon - from.lon)
  const h =
    Math.sin(dLat / 2) ** 2 + Math.cos(rad(from.lat)) * Math.cos(rad(to.lat)) * Math.sin(dLon / 2) ** 2
  return 2 * 6371 * Math.asin(Math.sqrt(h))
}

/**
 * Why a new stop cannot be inserted (null if it can). Same rules as the
 * backend: unused id and name, and the route runs directly from -> to.
 */
export function addedStopProblem(network: Network, change: AddStop): string | null {
  if (network.stops.some((stop) => stop.id === change.stop_id)) {
    return `stop id "${change.stop_id}" is already used`
  }
  const name = change.name.trim()
  if (name === '') return 'the new stop needs a name'
  if (network.stops.some((stop) => stop.name === name)) return `a stop called "${name}" already exists`
  const runs = network.connections.some(
    (c) =>
      c.route_id === change.route_id &&
      c.from_stop_id === change.from_stop_id &&
      c.to_stop_id === change.to_stop_id,
  )
  if (!runs) {
    return `route ${change.route_id} does not run directly from ${change.from_stop_id} to ${change.to_stop_id}`
  }
  return null
}

/**
 * The network as it is after inserting a new stop (frontend view only, e.g. so
 * later changes may refer to it). The route's direct links between the two
 * stops are replaced by links via the new stop, as in the backend.
 */
export function withAddedStop(network: Network, change: AddStop): Network {
  const { route_id: route, from_stop_id: a, to_stop_id: b, stop_id: n } = change
  let nextId = Math.max(0, ...network.connections.map((c) => c.id)) + 1
  const connections = network.connections.flatMap((c) => {
    if (c.route_id !== route) return [c]
    const forward = c.from_stop_id === a && c.to_stop_id === b
    const backward = c.from_stop_id === b && c.to_stop_id === a
    if (!forward && !backward) return [c]
    const [first, second] = forward
      ? [change.time_from_min, change.time_to_min]
      : [change.time_to_min, change.time_from_min]
    return [
      { id: nextId++, route_id: route, from_stop_id: c.from_stop_id, to_stop_id: n, travel_time_min: first },
      { id: nextId++, route_id: route, from_stop_id: n, to_stop_id: c.to_stop_id, travel_time_min: second },
    ]
  })
  const stop = { id: n, name: change.name.trim(), lat: change.lat, lon: change.lon, activity: 1 }
  return { ...network, stops: [...network.stops, stop], connections }
}
