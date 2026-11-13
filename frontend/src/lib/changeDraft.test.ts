import { describe, expect, it } from 'vitest'

import { smallNetwork as network } from '../test/smallNetwork'
import {
  buildChange,
  clickLink,
  clickStop,
  appendRouteStop,
  draftSelection,
  EMPTY_ROUTE,
  nextRouteId,
  removeLastRouteStop,
  routeColor,
  withRouteDraft,
  initialDraft,
  withFrom,
  nextStopId,
  placeStop,
  routeLinks,
  withLink,
  withRoute,
  withStopRoute,
  withType,
  type ChangeDraft,
} from './changeDraft'
import { linkKey } from './network'

const start = initialDraft(network)
const linkDraft = (type: ChangeDraft['type'] = 'remove_connection') => withType(start, type)

describe('initialDraft', () => {
  it('starts on "close stop" with the first stop by name and its first neighbour', () => {
    expect(start).toEqual({
      type: 'close_stop',
      stopId: 'ALP',
      fromId: 'ALP',
      toId: 'BRK',
      travelTime: '2', // fastest route on ALP→BRK
      bothDirections: true,
      awaitingTo: false,
      routeId: 'R1', // first route by id, with its current headway
      headway: '10',
      position: null,
      stopName: '',
      secondTime: '',
      route: EMPTY_ROUTE,
    })
  })
})

describe('form edits', () => {
  it('changing From picks its first neighbour as To and fills in the time', () => {
    const draft = withFrom(network, linkDraft(), 'CAS')
    expect([draft.fromId, draft.toId, draft.travelTime]).toEqual(['CAS', 'BRK', '4'])
  })

  it('choosing a link fills in its current travel time', () => {
    expect(withLink(network, linkDraft(), 'BRK', 'DUN').travelTime).toBe('5')
  })

  it('changing the type keeps the chosen stops', () => {
    const draft = withType(withLink(network, linkDraft(), 'BRK', 'DUN'), 'change_travel_time')
    expect([draft.fromId, draft.toId]).toEqual(['BRK', 'DUN'])
  })
})

describe('clickStop', () => {
  it('sets the stop when closing a stop', () => {
    const draft = clickStop(network, start, 'DUN')
    expect(draft.stopId).toBe('DUN')
    expect(draft.type).toBe('close_stop')
  })

  it('first click sets From (with a suggested To) and waits for To', () => {
    const draft = clickStop(network, linkDraft(), 'BRK')
    expect(draft.fromId).toBe('BRK')
    expect(draft.toId).toBe('ALP') // first neighbour by name
    expect(draft.awaitingTo).toBe(true)
  })

  it('second click on a neighbour sets To and the time', () => {
    const draft = clickStop(network, clickStop(network, linkDraft(), 'BRK'), 'DUN')
    expect([draft.fromId, draft.toId, draft.travelTime]).toEqual(['BRK', 'DUN', '5'])
    expect(draft.awaitingTo).toBe(false)
  })

  it('second click on a stop that is not a neighbour starts again as From', () => {
    // CAS is not next to ALP.
    const draft = clickStop(network, clickStop(network, linkDraft(), 'ALP'), 'CAS')
    expect([draft.fromId, draft.toId]).toEqual(['CAS', 'BRK'])
    expect(draft.awaitingTo).toBe(true)
  })

  it('a third click starts a new link', () => {
    let draft = clickStop(network, linkDraft(), 'BRK')
    draft = clickStop(network, draft, 'DUN')
    draft = clickStop(network, draft, 'BRK') // neighbour of DUN, but not waiting for To
    expect([draft.fromId, draft.toId]).toEqual(['BRK', 'ALP'])
    expect(draft.awaitingTo).toBe(true)
  })

  it('a form edit ends the waiting for To', () => {
    const draft = withType(clickStop(network, linkDraft(), 'BRK'), 'change_travel_time')
    expect(draft.awaitingTo).toBe(false)
  })
})

describe('clickLink', () => {
  it('switches "close stop" to "remove link"', () => {
    const draft = clickLink(network, start, 'BRK', 'CAS', 'R1')
    expect(draft.type).toBe('remove_connection')
    expect([draft.fromId, draft.toId]).toEqual(['BRK', 'CAS'])
  })

  it('keeps "travel time" and fills in the current time', () => {
    const draft = clickLink(network, linkDraft('change_travel_time'), 'ALP', 'BRK', 'R2')
    expect(draft.type).toBe('change_travel_time')
    expect(draft.travelTime).toBe('2')
  })

  it('ends a half-finished stop selection', () => {
    const draft = clickLink(network, clickStop(network, linkDraft(), 'CAS'), 'BRK', 'DUN', 'R2')
    expect(draft.awaitingTo).toBe(false)
  })
})

describe('draftSelection', () => {
  it('highlights the stop to close', () => {
    expect(draftSelection(clickStop(network, start, 'CAS'), network)).toEqual({
      stopIds: ['CAS'],
      link: null,
      routeId: null,
      newLink: null,
      newStop: null,
      newRoute: null,
    })
  })

  it('highlights both stops and the street of a link', () => {
    expect(draftSelection(withLink(network, linkDraft(), 'DUN', 'BRK'), network)).toEqual({
      stopIds: ['DUN', 'BRK'],
      link: linkKey('BRK', 'DUN'),
      routeId: null,
      newLink: null,
      newStop: null,
      newRoute: null,
    })
  })
})

describe('frequency', () => {
  const freq = withType(start, 'change_frequency')

  it('choosing a route fills in its current headway', () => {
    expect(withRoute(network, freq, 'R2')).toMatchObject({ routeId: 'R2', headway: '20' })
  })

  it('clicking a line selects its route', () => {
    expect(clickLink(network, freq, 'BRK', 'DUN', 'R2')).toMatchObject({
      type: 'change_frequency',
      routeId: 'R2',
      headway: '20',
    })
  })

  it('clicking a stop does nothing (a stop can serve several routes)', () => {
    expect(clickStop(network, freq, 'BRK')).toBe(freq)
  })

  it('highlights the whole route', () => {
    expect(draftSelection(freq, network)).toEqual({
      stopIds: [],
      link: null,
      routeId: 'R1',
      newLink: null,
      newStop: null,
      newRoute: null,
    })
  })

  it('builds the change and checks the 1-120 min range', () => {
    expect(buildChange({ ...freq, headway: '7.5' }, 0, network)).toEqual({
      type: 'change_frequency',
      route_id: 'R1',
      headway_min: 7.5,
    })
    for (const headway of ['', '0.5', '121', 'x']) {
      expect(buildChange({ ...freq, headway }, 0, network)).toBe('A bus can run every 1 to 120 minutes.')
    }
    expect(buildChange({ ...freq, routeId: '' }, 0, network)).toBe('Choose a route.')
  })
})

describe('add link', () => {
  // smallNetwork: R1 runs ALP-BRK-CAS, R2 runs ALP-BRK-DUN.
  const add = withType(start, 'add_connection')

  it('starts with an empty travel time (never pre-filled)', () => {
    expect(add.travelTime).toBe('')
  })

  it('two clicks on any two stops set From and To', () => {
    let draft = clickStop(network, add, 'CAS')
    expect(draft).toMatchObject({ fromId: 'CAS', awaitingTo: true })
    draft = clickStop(network, draft, 'CAS') // the same stop again: still From
    expect(draft).toMatchObject({ fromId: 'CAS', awaitingTo: true })
    draft = clickStop(network, draft, 'DUN') // not a neighbour: fine for a new link
    expect(draft).toMatchObject({ fromId: 'CAS', toId: 'DUN', awaitingTo: false })
  })

  it('clicking a line chooses the route', () => {
    expect(clickLink(network, add, 'BRK', 'DUN', 'R2').routeId).toBe('R2')
  })

  it('previews the planned link', () => {
    const draft = { ...add, fromId: 'CAS', toId: 'DUN' }
    expect(draftSelection(draft, network)).toEqual({
      stopIds: ['CAS', 'DUN'],
      link: null,
      routeId: null,
      newLink: { fromId: 'CAS', toId: 'DUN' },
      newStop: null,
      newRoute: null,
    })
  })

  it('builds the change with the backend rules and a required time', () => {
    const draft = { ...add, routeId: 'R1', fromId: 'CAS', toId: 'DUN' }
    expect(buildChange(draft, 0, network)).toBe('Travel time must be a number greater than 0.')
    expect(buildChange({ ...draft, travelTime: '6' }, 0, network)).toEqual({
      type: 'add_connection',
      route_id: 'R1',
      from_stop_id: 'CAS',
      to_stop_id: 'DUN',
      travel_time_min: 6,
      both_directions: true,
    })
    expect(buildChange({ ...draft, fromId: 'ALP', toId: 'BRK', travelTime: '6' }, 0, network)).toBe(
      'Not possible: route R1 already runs from ALP to BRK.',
    )
  })
})

describe('add stop', () => {
  // smallNetwork: R1 runs ALP-BRK-CAS (3, 4 min), R2 runs ALP-BRK-DUN.
  const add = withType(start, 'add_stop')

  it("lists a route's links once per street", () => {
    expect(routeLinks(network, 'R1')).toEqual([
      { fromId: 'ALP', toId: 'BRK' },
      { fromId: 'BRK', toId: 'CAS' },
    ])
  })

  it('a map click places the stop (rounded), a line click picks route and link', () => {
    let draft = placeStop(add, 0.12345678, 1.98765432)
    expect(draft.position).toEqual({ lat: 0.123457, lon: 1.987654 })
    draft = clickLink(network, draft, 'CAS', 'BRK', 'R1')
    expect(draft).toMatchObject({ routeId: 'R1', fromId: 'BRK', toId: 'CAS' })
    expect(clickStop(network, draft, 'ALP')).toBe(draft) // existing stops are not targets
  })

  it('choosing a route starts on its first link', () => {
    expect(withStopRoute(network, add, 'R2')).toMatchObject({ fromId: 'ALP', toId: 'BRK' })
  })

  it('next free id', () => {
    expect(nextStopId(network)).toBe('N1')
    const withN1 = { ...network, stops: [...network.stops, { ...network.stops[0], id: 'N1' }] }
    expect(nextStopId(withN1)).toBe('N2')
  })

  it('builds the change once placed, named and timed', () => {
    let draft = withStopRoute(network, add, 'R1')
    expect(buildChange(draft, 0, network)).toBe('Click the map to place the new stop.')
    draft = placeStop(draft, 0, 0.5)
    expect(buildChange(draft, 0, network)).toBe('Give the new stop a name.')
    draft = { ...draft, stopName: ' Mid Point ', travelTime: '1.5' }
    expect(buildChange(draft, 0, network)).toBe('Travel time must be a number greater than 0.')
    expect(buildChange({ ...draft, secondTime: '2' }, 0, network)).toEqual({
      type: 'add_stop',
      stop_id: 'N1',
      name: 'Mid Point',
      lat: 0,
      lon: 0.5,
      route_id: 'R1',
      from_stop_id: 'ALP',
      to_stop_id: 'BRK',
      time_from_min: 1.5,
      time_to_min: 2,
    })
    expect(buildChange({ ...draft, secondTime: '2', stopName: 'Castle' }, 0, network)).toBe(
      'Not possible: a stop called "Castle" already exists.',
    )
  })

  it('previews the position and the link', () => {
    const draft = placeStop(withStopRoute(network, add, 'R1'), 0, 0.5)
    expect(draftSelection(draft, network)).toMatchObject({
      link: linkKey('ALP', 'BRK'),
      newStop: { lat: 0, lon: 0.5 },
    })
  })
})

describe('buildChange', () => {
  it('builds each change type', () => {
    expect(buildChange(clickStop(network, start, 'CAS'), 0, network)).toEqual({
      type: 'close_stop',
      stop_id: 'CAS',
    })
    expect(buildChange(withLink(network, linkDraft(), 'BRK', 'DUN'), 0, network)).toEqual({
      type: 'remove_connection',
      from_stop_id: 'BRK',
      to_stop_id: 'DUN',
      both_directions: true,
    })
    const retimed = { ...linkDraft('change_travel_time'), travelTime: '7.5', bothDirections: false }
    expect(buildChange(retimed, 0, network)).toEqual({
      type: 'change_travel_time',
      from_stop_id: 'ALP',
      to_stop_id: 'BRK',
      travel_time_min: 7.5,
      both_directions: false,
    })
  })

  it('rejects invalid travel times', () => {
    for (const travelTime of ['', ' ', '0', '-3', 'abc', '601']) {
      expect(typeof buildChange({ ...linkDraft('change_travel_time'), travelTime }, 0, network)).toBe('string')
    }
    expect(typeof buildChange({ ...linkDraft('change_travel_time'), travelTime: '600' }, 0, network)).toBe(
      'object',
    )
  })

  it('rejects a link without a To stop', () => {
    expect(buildChange({ ...linkDraft(), toId: '' }, 0, network)).toBe('Choose both stops of the connection.')
  })

  it('enforces the change limit', () => {
    expect(buildChange(start, 20, network)).toBe('A scenario can have at most 20 changes.')
    expect(typeof buildChange(start, 19, network)).toBe('object')
  })
})

describe('add route', () => {
  const route = withType(start, 'add_route')
  const clicked = (...ids: string[]) => ids.reduce((draft, id) => clickStop(network, draft, id), route)
  const ready = withRouteDraft(clicked('CAS', 'BRK', 'DUN'), { name: 'Green', headway: '12', times: ['4', '5'] })

  it('map clicks add stops in order; a stop already on the route is ignored', () => {
    expect(clicked('CAS', 'BRK', 'CAS').route).toMatchObject({ stopIds: ['CAS', 'BRK'], times: [''], isLoop: false })
  })

  it('clicking the first stop again (3+ stops) makes a loop', () => {
    expect(clicked('CAS', 'BRK', 'DUN', 'CAS').route).toMatchObject({ stopIds: ['CAS', 'BRK', 'DUN'], isLoop: true })
  })

  it('lines do nothing: a new route is drawn stop by stop', () => {
    expect(clickLink(network, route, 'ALP', 'BRK', 'R1')).toBe(route)
  })

  it('removing the last stop drops its stretch, and the loop below 3 stops', () => {
    const loop = withRouteDraft(ready, { isLoop: true })
    expect(removeLastRouteStop(loop).route).toMatchObject({ stopIds: ['CAS', 'BRK'], times: ['4'], isLoop: false })
    expect(removeLastRouteStop(withRouteDraft(route, { stopIds: ['CAS'] })).route.stopIds).toEqual([])
  })

  it('stops at 30 stops', () => {
    const full = withRouteDraft(route, { stopIds: Array.from({ length: 30 }, (_, i) => `S${i}`) })
    expect(appendRouteStop(full, 'CAS')).toBe(full)
  })

  it('picks the next free id and colour automatically, or the chosen colour', () => {
    expect(nextRouteId(network)).toBe('R3')
    expect(routeColor(network, route)).toBe('#7c3aed')
    const used = { ...network, routes: [...network.routes, { id: 'R3', name: 'X', color: '#7C3AED', headway_min: 5 }] }
    expect(routeColor(used, route)).toBe('#db2777')
    expect(routeColor(network, withRouteDraft(route, { color: '#0d9488' }))).toBe('#0d9488')
  })

  it('previews the route in its colour and rings its stops', () => {
    expect(draftSelection(ready, network)).toMatchObject({
      stopIds: ['CAS', 'BRK', 'DUN'],
      newRoute: { stopIds: ['CAS', 'BRK', 'DUN'], color: '#7c3aed', isLoop: false },
    })
  })

  it('builds the change', () => {
    expect(buildChange(ready, 0, network)).toEqual({
      type: 'add_route',
      route_id: 'R3',
      name: 'Green',
      color: '#7c3aed',
      headway_min: 12,
      stop_ids: ['CAS', 'BRK', 'DUN'],
      travel_times_min: [4, 5],
      is_loop: false,
      both_directions: true,
    })
    const loop = withRouteDraft(ready, { isLoop: true, loopTime: '6' })
    expect(buildChange(loop, 0, network)).toMatchObject({ travel_times_min: [4, 5, 6], is_loop: true })
  })

  it('explains what is missing, naming the stretch without a time', () => {
    const error = (patch: Parameters<typeof withRouteDraft>[1]) => buildChange(withRouteDraft(ready, patch), 0, network)
    expect(error({ name: ' ' })).toBe('Give the new route a name.')
    expect(error({ headway: '' })).toBe('Enter how often a bus runs: every 1 to 120 minutes.')
    expect(error({ stopIds: ['CAS'], times: [] })).toBe('Click at least 2 stops on the map, in the order the bus calls.')
    expect(error({ times: ['4', ''] })).toBe('Brook Street → Dunes: Travel time must be a number greater than 0.')
    expect(error({ isLoop: true })).toBe('Dunes → Castle: Travel time must be a number greater than 0.')
    expect(error({ name: 'Blue' })).toBe('Not possible: a route called "Blue" already exists.')
  })
})
