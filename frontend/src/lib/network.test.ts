import { describe, expect, it } from 'vitest'

import { smallNetwork } from '../test/smallNetwork'
import type { Network } from '../types/network'
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
