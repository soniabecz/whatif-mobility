// Pure helpers over the network data. No React, no API calls.

import type { Network, Stop } from '../types/network'
import type { ScenarioChange } from '../types/scenario'

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
}

export function scenarioHighlights(changes: ScenarioChange[]): ScenarioHighlights {
  const highlights: ScenarioHighlights = {
    closedStopIds: new Set(),
    removedLinks: new Set(),
    retimedLinks: new Set(),
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
        break // affects waiting, not a street: nothing to highlight on the map
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
  }
}

function arrow(bothDirections: boolean): string {
  return bothDirections ? '↔' : '→'
}
