import { describe, expect, it } from 'vitest'

import type { JourneyLeg, JourneyPlan, WalkLeg } from '../types/journey'
import { describeWalking, journeySteps, journeyStopIds } from './journeyPlan'

function leg(routeId: string, stopIds: string[]): JourneyLeg {
  return { route_id: routeId, stop_ids: stopIds, travel_time_min: 5, wait_min: 0, passes_closed_stop_ids: [] }
}

function walk(from: string, to: string, beforeLeg: number): WalkLeg {
  return { from_stop_id: from, to_stop_id: to, distance_m: 400, minutes: 4.8, before_leg: beforeLeg }
}

function plan(legs: JourneyLeg[], walks: WalkLeg[]): JourneyPlan {
  return {
    travel_time_min: 20, in_vehicle_min: 10, wait_min: 0, walk_min: 9.6,
    walks, transfers: Math.max(legs.length - 1, 0), transfer_penalty_min: 2, legs,
  }
}

describe('journeySteps', () => {
  it('puts walks at the start, between buses and at the end in order', () => {
    const steps = journeySteps(
      plan([leg('R1', ['A', 'B']), leg('R2', ['C', 'D'])], [walk('S', 'A', 0), walk('B', 'C', 1), walk('D', 'E', 2)]),
    )
    expect(steps.map((s) => (s.kind === 'walk' ? `walk ${s.walk.from_stop_id}-${s.walk.to_stop_id}` : s.leg.route_id)))
      .toEqual(['walk S-A', 'R1', 'walk B-C', 'R2', 'walk D-E'])
    expect(steps.filter((s) => s.kind === 'bus').map((s) => s.kind === 'bus' && s.index)).toEqual([0, 1])
  })

  it('handles a journey walked the whole way', () => {
    expect(journeySteps(plan([], [walk('A', 'B', 0)]))).toEqual([{ kind: 'walk', walk: walk('A', 'B', 0) }])
  })
})

describe('journeyStopIds', () => {
  it('lists the stops in order without repeating a stop where a walk meets a bus', () => {
    const p = plan([leg('R1', ['A', 'X', 'B']), leg('R2', ['C', 'D'])], [walk('S', 'A', 0), walk('B', 'C', 1)])
    expect(journeyStopIds(p)).toEqual(['S', 'A', 'X', 'B', 'C', 'D'])
    expect(journeyStopIds(null)).toEqual([])
  })
})

describe('describeWalking', () => {
  const settings = { speed_kmh: 5, max_walk_m: 1000, max_transfer_walk_m: 500, between_open_stops: true }

  it('describes walking everywhere, closed stops only, or none', () => {
    expect(describeWalking(settings)).toBe(
      'Passengers may walk up to 1,000 m at the start or end and up to 500 m between two buses ' +
        '(at 5 km/h, distance = straight line × 1.3).',
    )
    expect(describeWalking({ ...settings, between_open_stops: false })).toBe(
      'Passengers walk only from or to a closed stop, up to 1,000 m (at 5 km/h, distance = straight line × 1.3).',
    )
    expect(describeWalking(null)).toBe('Nobody walks: journeys to or from a closed stop are left out.')
  })
})
