import { describe, expect, it } from 'vitest'

import { smallNetwork } from '../test/smallNetwork'
import type { Network } from '../types/network'
import type { AddRoute, ScenarioChange } from '../types/scenario'
import {
  addedConnectionProblem,
  addedRouteProblem,
  addedStopProblem,
  compactStops,
  stopMarkerSize,
  filterRoutes,
  applyAddedChanges,
  withAddedRoute,
  withAddedStop,
  currentTravelTime,
  describeChange,
  exampleRequest,
  linkKey,
  neighbours,
  routeSegments,
  scenarioHighlights,
  sortedRoutes,
  sortedStops,
  stopLabel,
  stopsById,
} from './network'

const network = smallNetwork

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

  it('collects new headways per route, the last change winning', () => {
    const highlights = scenarioHighlights([
      { type: 'change_frequency', route_id: 'R1', headway_min: 5 },
      { type: 'change_frequency', route_id: 'R2', headway_min: 30 },
      { type: 'change_frequency', route_id: 'R1', headway_min: 4 },
    ])
    expect([...highlights.headways]).toEqual([
      ['R1', 4],
      ['R2', 30],
    ])
  })

  it('is empty without changes', () => {
    const highlights = scenarioHighlights([])
    expect(highlights.closedStopIds.size).toBe(0)
    expect(highlights.removedLinks.size).toBe(0)
    expect(highlights.retimedLinks.size).toBe(0)
    expect(highlights.headways.size).toBe(0)
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

  it('describes an added connection', () => {
    expect(
      describeChange(
        {
          type: 'add_connection',
          route_id: 'R1',
          from_stop_id: 'CAS',
          to_stop_id: 'DUN',
          travel_time_min: 6,
          both_directions: true,
        },
        stops,
      ),
    ).toBe('Add R1: Castle ↔ Dunes, 6 min')
  })

  it('describes a frequency change by route', () => {
    expect(
      describeChange({ type: 'change_frequency', route_id: 'R2', headway_min: 7.5 }, stops),
    ).toBe('R2: a bus every 7.5 min')
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

describe('addedConnectionProblem', () => {
  it('allows an extension from a stop on the route', () => {
    // R1 serves ALP, BRK, CAS; DUN is new for R1.
    expect(addedConnectionProblem(network, 'R1', 'CAS', 'DUN', true)).toBeNull()
  })

  it('needs one stop on the route, two different stops and a new link', () => {
    const lonely = { ...network, connections: network.connections.filter((c) => c.route_id === 'R2') }
    expect(addedConnectionProblem(lonely, 'R1', 'CAS', 'DUN', true)).toBe(
      'route R1 stops at neither CAS nor DUN',
    )
    expect(addedConnectionProblem(network, 'R1', 'CAS', 'CAS', true)).toBe(
      'a connection needs two different stops',
    )
    expect(addedConnectionProblem(network, 'R1', 'BRK', 'ALP', false)).toBe(
      'route R1 already runs from BRK to ALP',
    )
  })
})

describe('new stops', () => {
  const change = {
    type: 'add_stop' as const,
    stop_id: 'N1',
    name: 'New Square',
    lat: 0,
    lon: 1.5,
    route_id: 'R1',
    from_stop_id: 'BRK',
    to_stop_id: 'CAS',
    time_from_min: 1.5,
    time_to_min: 3,
  }

  it('describes a new stop', () => {
    expect(describeChange(change, stops)).toBe(
      'New stop New Square on R1: Brook Street 1.5 min → 3 min Castle',
    )
  })

  it('inserts the stop into the route in both directions', () => {
    const after = withAddedStop(network, change)
    expect(after.stops.map((s) => s.id)).toContain('N1')
    const r1 = after.connections
      .filter((c) => c.route_id === 'R1')
      .map((c) => `${c.from_stop_id}>${c.to_stop_id}:${c.travel_time_min}`)
    expect(r1).not.toContain('BRK>CAS:4')
    expect(r1).toEqual(expect.arrayContaining(['BRK>N1:1.5', 'N1>CAS:3', 'CAS>N1:3', 'N1>BRK:1.5']))
    expect(network.stops).toHaveLength(4) // the original is untouched
  })

  it('checks the backend rules', () => {
    expect(addedStopProblem(network, change)).toBeNull()
    expect(addedStopProblem(network, { ...change, to_stop_id: 'DUN' })).toBe(
      'route R1 does not run directly from BRK to DUN',
    )
  })
})

describe('new routes', () => {
  // CAS -> ALP -> DUN: CAS and DUN are not linked today.
  const route: AddRoute = {
    type: 'add_route',
    route_id: 'R3',
    name: 'Green',
    color: '#0d9488',
    headway_min: 12,
    stop_ids: ['CAS', 'ALP', 'DUN'],
    travel_times_min: [6, 4.5],
    is_loop: false,
    both_directions: true,
  }

  it('describes a new route, a loop and a one-way route', () => {
    expect(describeChange(route, stops)).toBe(
      'New route R3 Green, every 12 min: Castle ↔ Alpine Road ↔ Dunes (6 + 4.5 min)',
    )
    const loop = { ...route, travel_times_min: [6, 4.5, 3], is_loop: true, both_directions: false }
    expect(describeChange(loop, stops)).toBe(
      'New route R3 Green, every 12 min: Castle → Alpine Road → Dunes → Castle (loop, 6 + 4.5 + 3 min)',
    )
  })

  it('adds the route and its links in both directions', () => {
    const after = withAddedRoute(network, route)
    expect(after.routes.at(-1)).toEqual({ id: 'R3', name: 'Green', color: '#0d9488', headway_min: 12 })
    const r3 = after.connections
      .filter((c) => c.route_id === 'R3')
      .map((c) => `${c.from_stop_id}>${c.to_stop_id}:${c.travel_time_min}`)
    expect(r3).toEqual(['CAS>ALP:6', 'ALP>CAS:6', 'ALP>DUN:4.5', 'DUN>ALP:4.5'])
    expect(new Set(after.connections.map((c) => c.id)).size).toBe(after.connections.length)
    expect(network.routes).toHaveLength(2) // the original is untouched
  })

  it('closes a loop and runs one way only when asked', () => {
    const loop = { ...route, travel_times_min: [6, 4.5, 3], is_loop: true, both_directions: false }
    const r3 = withAddedRoute(network, loop).connections.filter((c) => c.route_id === 'R3')
    expect(r3.map((c) => `${c.from_stop_id}>${c.to_stop_id}`)).toEqual(['CAS>ALP', 'ALP>DUN', 'DUN>CAS'])
  })

  it('lets later changes use added stops and routes, in order', () => {
    const stop: ScenarioChange = {
      type: 'add_stop', stop_id: 'N1', name: 'New Square', lat: 0, lon: 0.5,
      route_id: 'R3', from_stop_id: 'CAS', to_stop_id: 'ALP', time_from_min: 2, time_to_min: 4,
    }
    const after = applyAddedChanges(network, [route, stop])
    expect(after.routes.map((r) => r.id)).toEqual(['R1', 'R2', 'R3'])
    expect(after.connections.some((c) => c.route_id === 'R3' && c.from_stop_id === 'N1')).toBe(true)
  })

  it('checks the backend rules', () => {
    expect(addedRouteProblem(network, route)).toBeNull()
    const problem = (overrides: Partial<AddRoute>) => addedRouteProblem(network, { ...route, ...overrides })
    expect(problem({ route_id: 'R1' })).toBe('route id "R1" is already used')
    expect(problem({ name: ' Blue ' })).toBe('a route called "Blue" already exists')
    expect(problem({ name: ' ' })).toBe('the new route needs a name')
    expect(problem({ color: 'teal' })).toBe('"teal" is not a colour')
    expect(problem({ headway_min: 0.5 })).toBe('a bus must run every 1 to 120 minutes')
    expect(problem({ stop_ids: ['CAS'], travel_times_min: [] })).toBe('a route needs 2 to 30 stops')
    expect(problem({ stop_ids: ['CAS', 'ALP', 'CAS'] })).toBe('a route cannot stop at the same stop twice')
    expect(problem({ stop_ids: ['CAS', 'XYZ', 'DUN'] })).toBe('unknown stop "XYZ"')
    expect(problem({ travel_times_min: [6] })).toBe('3 stops need 2 travel times')
    expect(problem({ is_loop: true })).toBe('3 stops need 3 travel times')
    expect(problem({ stop_ids: ['CAS', 'ALP'], travel_times_min: [6, 1], is_loop: true })).toBe(
      'a loop needs at least 3 stops',
    )
    expect(problem({ travel_times_min: [6, 0] })).toContain('more than 0')
  })
})

describe('sortedRoutes and exampleRequest', () => {
  it('orders line numbers naturally', () => {
    const lines = { ...network, routes: ['T10', 'T2', 'T1'].map((id) => ({ id, name: id, color: '#000000', headway_min: 10 })) }
    expect(sortedRoutes(lines).map((route) => route.id)).toEqual(['T1', 'T2', 'T10'])
  })

  it('builds the AI example from a real link of the network', () => {
    expect(exampleRequest(network)).toBe('e.g. "Roadworks make Alpine Road – Brook Street twice as slow"')
    expect(exampleRequest({ ...network, connections: [] })).toBe('e.g. "Close the busiest stop"')
  })
})

describe('filterRoutes', () => {
  const lines = [
    { id: 'B199', name: 'Bus 199' },
    { id: 'B100', name: 'Bus 100' },
    { id: 'T2', name: 'Tram 2' },
  ]

  it('keeps every route for an empty or blank query', () => {
    expect(filterRoutes(lines, '')).toEqual(lines)
    expect(filterRoutes(lines, '   ')).toEqual(lines)
  })

  it('matches the id or the name, ignoring case and outer spaces', () => {
    expect(filterRoutes(lines, '199').map((r) => r.id)).toEqual(['B199'])
    expect(filterRoutes(lines, ' tram ').map((r) => r.id)).toEqual(['T2'])
    expect(filterRoutes(lines, 'b1').map((r) => r.id)).toEqual(['B199', 'B100'])
    expect(filterRoutes(lines, 'xyz')).toEqual([])
  })
})

describe('compactStops', () => {
  it('only shrinks stops of a large network below the full-size zoom', () => {
    expect(compactStops(714, 12)).toBe(true)
    expect(compactStops(714, 13)).toBe(true)
    expect(compactStops(714, 14)).toBe(false)
    expect(compactStops(200, 10)).toBe(false) // the limit itself is not large
    expect(compactStops(122, 11)).toBe(false) // trams
    expect(compactStops(16, 5)).toBe(false) // sample city
  })
})

describe('stopMarkerSize', () => {
  it('keeps the usual sizes on a normal map', () => {
    expect(stopMarkerSize(null, false)).toEqual({ radius: 6, weight: 2.5 })
    expect(stopMarkerSize('unaffected', false)).toEqual({ radius: 6, weight: 2.5 })
    expect(stopMarkerSize('slower', false)).toEqual({ radius: 9, weight: 3 })
    expect(stopMarkerSize('closed', false)).toEqual({ radius: 9, weight: 3 })
  })

  it('shrinks plain and coloured stops on a compact map, but not closed ones', () => {
    expect(stopMarkerSize(null, true)).toEqual({ radius: 3, weight: 1.5 })
    expect(stopMarkerSize('unaffected', true)).toEqual({ radius: 3, weight: 1.5 })
    for (const level of ['slower', 'faster', 'impossible'] as const) {
      expect(stopMarkerSize(level, true)).toEqual({ radius: 5, weight: 1.5 })
    }
    expect(stopMarkerSize('closed', true)).toEqual({ radius: 9, weight: 3 })
  })
})
