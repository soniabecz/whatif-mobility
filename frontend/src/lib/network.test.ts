import { describe, expect, it } from 'vitest'

import type { Connection, Network } from '../types/network'
import type { ScenarioChange } from '../types/scenario'
import {
  currentTravelTime,
  describeChange,
  linkKey,
  neighbours,
  routeSegments,
  scenarioHighlights,
  sortedStops,
  stopLabel,
  stopsById,
} from './network'

// Small hand-made network (ids deliberately not in name order):
//
//   ALP --R1 3 min / R2 2 min-- BRK --R1 4-- CAS
//                                |
//                               R2 5
//                                |
//                               DUN
//
// ALP–BRK is served by two routes with different times.
let nextId = 1
function both(routeId: string, a: string, b: string, minutes: number): Connection[] {
  return [
    { id: nextId++, route_id: routeId, from_stop_id: a, to_stop_id: b, travel_time_min: minutes },
    { id: nextId++, route_id: routeId, from_stop_id: b, to_stop_id: a, travel_time_min: minutes },
  ]
}

const network: Network = {
  stops: [
    { id: 'BRK', name: 'Brook Street', lat: 0, lon: 1 },
    { id: 'ALP', name: 'Alpine Road', lat: 0, lon: 0 },
    { id: 'DUN', name: 'Dunes', lat: -1, lon: 1 },
    { id: 'CAS', name: 'Castle', lat: 0, lon: 2 },
  ],
  routes: [
    { id: 'R1', name: 'Red', color: '#ff0000' },
    { id: 'R2', name: 'Blue', color: '#0000ff' },
  ],
  connections: [
    ...both('R1', 'ALP', 'BRK', 3),
    ...both('R1', 'BRK', 'CAS', 4),
    ...both('R2', 'ALP', 'BRK', 2),
    ...both('R2', 'BRK', 'DUN', 5),
  ],
}

const stops = stopsById(network)

describe('linkKey', () => {
  it('is the same in both directions', () => {
    expect(linkKey('ALP', 'BRK')).toBe(linkKey('BRK', 'ALP'))
  })

  it('differs for different streets', () => {
    expect(linkKey('ALP', 'BRK')).not.toBe(linkKey('ALP', 'CAS'))
  })
})

describe('stop lookups', () => {
  it('finds stops by id', () => {
    expect(stops.get('CAS')?.name).toBe('Castle')
    expect(stops.size).toBe(4)
  })

  it('labels a stop by name, falling back to the id', () => {
    expect(stopLabel(stops, 'DUN')).toBe('Dunes')
    expect(stopLabel(stops, 'XYZ')).toBe('XYZ')
  })

  it('sorts stops by name without changing the network', () => {
    expect(sortedStops(network).map((s) => s.id)).toEqual(['ALP', 'BRK', 'CAS', 'DUN'])
    expect(network.stops[0].id).toBe('BRK')
  })
})

describe('neighbours', () => {
  it('lists stops one connection away, once each, sorted by name', () => {
    // BRK reaches ALP on two routes; it must appear only once.
    expect(neighbours(network, 'BRK').map((s) => s.id)).toEqual(['ALP', 'CAS', 'DUN'])
  })

  it('follows the direction of connections', () => {
    expect(neighbours(network, 'CAS').map((s) => s.id)).toEqual(['BRK'])
  })

  it('is empty for an unknown stop', () => {
    expect(neighbours(network, 'XYZ')).toEqual([])
  })
})

describe('currentTravelTime', () => {
  it('uses the fastest route when several serve the link', () => {
    expect(currentTravelTime(network, 'ALP', 'BRK')).toBe(2)
  })

  it('returns the single route time otherwise', () => {
    expect(currentTravelTime(network, 'BRK', 'CAS')).toBe(4)
  })

  it('returns null when there is no direct connection', () => {
    expect(currentTravelTime(network, 'ALP', 'CAS')).toBeNull()
  })
})

describe('routeSegments', () => {
  it('draws one line per route per street, whatever the direction', () => {
    const keys = routeSegments(network).map((s) => s.key)
    expect(keys).toHaveLength(4) // 8 directed connections
    expect(new Set(keys).size).toBe(4)
    expect(keys).toContain(`R1:${linkKey('ALP', 'BRK')}`)
    expect(keys).toContain(`R2:${linkKey('ALP', 'BRK')}`)
  })

  it('keeps the route time and the stop objects', () => {
    const blue = routeSegments(network).find((s) => s.key === `R2:${linkKey('ALP', 'BRK')}`)
    expect(blue?.travelTimeMin).toBe(2)
    expect(blue?.from.id).toBe('ALP')
    expect(blue?.to.id).toBe('BRK')
  })

  it('skips connections to stops that are missing', () => {
    const broken: Network = {
      ...network,
      connections: [
        { id: 99, route_id: 'R1', from_stop_id: 'ALP', to_stop_id: 'XYZ', travel_time_min: 1 },
      ],
    }
    expect(routeSegments(broken)).toEqual([])
  })
})

describe('scenarioHighlights', () => {
  it('sorts changes into closed stops, removed and retimed streets', () => {
    const changes: ScenarioChange[] = [
      { type: 'close_stop', stop_id: 'BRK' },
      { type: 'remove_connection', from_stop_id: 'CAS', to_stop_id: 'BRK', both_directions: true },
      {
        type: 'change_travel_time',
        from_stop_id: 'BRK',
        to_stop_id: 'DUN',
        travel_time_min: 9,
        both_directions: false,
      },
    ]
    const highlights = scenarioHighlights(changes)
    expect([...highlights.closedStopIds]).toEqual(['BRK'])
    // Streets are direction-independent keys.
    expect(highlights.removedLinks.has(linkKey('BRK', 'CAS'))).toBe(true)
    expect(highlights.retimedLinks.has(linkKey('DUN', 'BRK'))).toBe(true)
  })

  it('is empty without changes', () => {
    const highlights = scenarioHighlights([])
    expect(highlights.closedStopIds.size).toBe(0)
    expect(highlights.removedLinks.size).toBe(0)
    expect(highlights.retimedLinks.size).toBe(0)
  })
})

describe('describeChange', () => {
  it('describes closing a stop by name', () => {
    expect(describeChange({ type: 'close_stop', stop_id: 'CAS' }, stops)).toBe('Close Castle')
  })

  it('shows ↔ for both directions and → for one', () => {
    expect(
      describeChange(
        { type: 'remove_connection', from_stop_id: 'ALP', to_stop_id: 'BRK', both_directions: true },
        stops,
      ),
    ).toBe('Remove Alpine Road ↔ Brook Street')
    expect(
      describeChange(
        { type: 'remove_connection', from_stop_id: 'ALP', to_stop_id: 'BRK', both_directions: false },
        stops,
      ),
    ).toBe('Remove Alpine Road → Brook Street')
  })

  it('includes the new travel time', () => {
    expect(
      describeChange(
        {
          type: 'change_travel_time',
          from_stop_id: 'BRK',
          to_stop_id: 'DUN',
          travel_time_min: 7.5,
          both_directions: true,
        },
        stops,
      ),
    ).toBe('Brook Street ↔ Dunes: 7.5 min')
  })
})
