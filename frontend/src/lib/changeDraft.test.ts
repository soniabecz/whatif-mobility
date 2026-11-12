import { describe, expect, it } from 'vitest'

import { smallNetwork as network } from '../test/smallNetwork'
import {
  buildChange,
  clickLink,
  clickStop,
  draftSelection,
  initialDraft,
  withFrom,
  withLink,
  withRoute,
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
    expect(draftSelection(clickStop(network, start, 'CAS'))).toEqual({
      stopIds: ['CAS'],
      link: null,
      routeId: null,
    })
  })

  it('highlights both stops and the street of a link', () => {
    expect(draftSelection(withLink(network, linkDraft(), 'DUN', 'BRK'))).toEqual({
      stopIds: ['DUN', 'BRK'],
      link: linkKey('BRK', 'DUN'),
      routeId: null,
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
    expect(draftSelection(freq)).toEqual({ stopIds: [], link: null, routeId: 'R1' })
  })

  it('builds the change and checks the 1-120 min range', () => {
    expect(buildChange({ ...freq, headway: '7.5' }, 0)).toEqual({
      type: 'change_frequency',
      route_id: 'R1',
      headway_min: 7.5,
    })
    for (const headway of ['', '0.5', '121', 'x']) {
      expect(buildChange({ ...freq, headway }, 0)).toBe('A bus can run every 1 to 120 minutes.')
    }
    expect(buildChange({ ...freq, routeId: '' }, 0)).toBe('Choose a route.')
  })
})

describe('buildChange', () => {
  it('builds each change type', () => {
    expect(buildChange(clickStop(network, start, 'CAS'), 0)).toEqual({
      type: 'close_stop',
      stop_id: 'CAS',
    })
    expect(buildChange(withLink(network, linkDraft(), 'BRK', 'DUN'), 0)).toEqual({
      type: 'remove_connection',
      from_stop_id: 'BRK',
      to_stop_id: 'DUN',
      both_directions: true,
    })
    const retimed = { ...linkDraft('change_travel_time'), travelTime: '7.5', bothDirections: false }
    expect(buildChange(retimed, 0)).toEqual({
      type: 'change_travel_time',
      from_stop_id: 'ALP',
      to_stop_id: 'BRK',
      travel_time_min: 7.5,
      both_directions: false,
    })
  })

  it('rejects invalid travel times', () => {
    for (const travelTime of ['', ' ', '0', '-3', 'abc', '601']) {
      expect(typeof buildChange({ ...linkDraft('change_travel_time'), travelTime }, 0)).toBe('string')
    }
    expect(typeof buildChange({ ...linkDraft('change_travel_time'), travelTime: '600' }, 0)).toBe(
      'object',
    )
  })

  it('rejects a link without a To stop', () => {
    expect(buildChange({ ...linkDraft(), toId: '' }, 0)).toBe('Choose both stops of the connection.')
  })

  it('enforces the change limit', () => {
    expect(buildChange(start, 20)).toBe('A scenario can have at most 20 changes.')
    expect(typeof buildChange(start, 19)).toBe('object')
  })
})
