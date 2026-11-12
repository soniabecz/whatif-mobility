// Shared test fixture (only imported by *.test.ts files, never by the app).
// Ids deliberately not in name order:
//
//   ALP --R1 3 min / R2 2 min-- BRK --R1 4-- CAS
//                                |
//                               R2 5
//                                |
//                               DUN
//
// ALP–BRK is served by two routes with different times.

import type { Connection, Network } from '../types/network'

let nextId = 1
function both(routeId: string, a: string, b: string, minutes: number): Connection[] {
  return [
    { id: nextId++, route_id: routeId, from_stop_id: a, to_stop_id: b, travel_time_min: minutes },
    { id: nextId++, route_id: routeId, from_stop_id: b, to_stop_id: a, travel_time_min: minutes },
  ]
}

export const smallNetwork: Network = {
  stops: [
    { id: 'BRK', name: 'Brook Street', lat: 0, lon: 1, activity: 1 },
    { id: 'ALP', name: 'Alpine Road', lat: 0, lon: 0, activity: 1 },
    { id: 'DUN', name: 'Dunes', lat: -1, lon: 1, activity: 1 },
    { id: 'CAS', name: 'Castle', lat: 0, lon: 2, activity: 1 },
  ],
  routes: [
    { id: 'R1', name: 'Red', color: '#ff0000', headway_min: 10 },
    { id: 'R2', name: 'Blue', color: '#0000ff', headway_min: 20 },
  ],
  connections: [
    ...both('R1', 'ALP', 'BRK', 3),
    ...both('R1', 'BRK', 'CAS', 4),
    ...both('R2', 'ALP', 'BRK', 2),
    ...both('R2', 'BRK', 'DUN', 5),
  ],
}
