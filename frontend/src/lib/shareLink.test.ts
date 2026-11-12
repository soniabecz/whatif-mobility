import { describe, expect, it } from 'vitest'

import { smallNetwork as network } from '../test/smallNetwork'
import type { Network } from '../types/network'
import type { ScenarioChange } from '../types/scenario'
import { decodeChanges, encodeChanges, readShareParam, sharePath } from './shareLink'

const all: ScenarioChange[] = [
  { type: 'close_stop', stop_id: 'CAS' },
  { type: 'remove_connection', from_stop_id: 'ALP', to_stop_id: 'BRK', both_directions: true },
  { type: 'remove_connection', from_stop_id: 'BRK', to_stop_id: 'DUN', both_directions: false },
  {
    type: 'change_travel_time',
    from_stop_id: 'BRK',
    to_stop_id: 'CAS',
    travel_time_min: 9,
    both_directions: true,
  },
  {
    type: 'change_travel_time',
    from_stop_id: 'DUN',
    to_stop_id: 'BRK',
    travel_time_min: 7.5,
    both_directions: false,
  },
  { type: 'change_frequency', route_id: 'R2', headway_min: 7.5 },
]

describe('encodeChanges', () => {
  it('writes a short, readable text', () => {
    expect(encodeChanges(all)).toBe(
      'close:CAS~remove:ALP-BRK~remove:BRK-DUN:oneway~time:BRK-CAS:9~time:DUN-BRK:7.5:oneway~freq:R2:7.5',
    )
  })

  it('is empty without changes', () => {
    expect(encodeChanges([])).toBe('')
  })

  it('only uses characters browsers never percent-encode in a query', () => {
    expect(encodeChanges(all)).toMatch(/^[A-Za-z0-9:~.\-%]*$/)
  })
})

describe('round trip', () => {
  it('restores every change type, in order', () => {
    expect(decodeChanges(encodeChanges(all), network)).toEqual({ ok: true, changes: all })
  })

  it('restores stop ids that contain separator characters', () => {
    const odd: Network = {
      ...network,
      stops: [
        { id: 'A-1:x', name: 'Odd A', lat: 0, lon: 0 },
        { id: 'B~2 é', name: 'Odd B', lat: 0, lon: 1 },
      ],
      connections: [
        { id: 1, route_id: 'R1', from_stop_id: 'A-1:x', to_stop_id: 'B~2 é', travel_time_min: 3 },
      ],
    }
    const changes: ScenarioChange[] = [
      { type: 'close_stop', stop_id: 'B~2 é' },
      { type: 'remove_connection', from_stop_id: 'A-1:x', to_stop_id: 'B~2 é', both_directions: false },
    ]
    const encoded = encodeChanges(changes)
    expect(encoded).not.toMatch(/[ é]/)
    expect(decodeChanges(encoded, odd)).toEqual({ ok: true, changes })
  })
})

describe('sharePath and readShareParam', () => {
  it('puts the changes in the s parameter and leaves it out when empty', () => {
    expect(sharePath('/', [all[0]])).toBe('/?s=close:CAS')
    expect(sharePath('/', [])).toBe('/')
  })

  it('reads the raw value, without decoding escaped separators', () => {
    expect(readShareParam('?s=close:A%2D1')).toBe('close:A%2D1')
    expect(readShareParam('?x=1&s=close:CAS&y=2')).toBe('close:CAS')
    expect(readShareParam('?s=')).toBe('')
    expect(readShareParam('')).toBeNull()
    expect(readShareParam('?ss=close:CAS')).toBeNull()
  })
})

describe('decodeChanges rejects', () => {
  const rejects = (raw: string, message: string) => {
    const result = decodeChanges(raw, network)
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.error).toContain(message)
  }

  it('unknown types and malformed changes', () => {
    rejects('open:CAS', '"open" is not a known type')
    rejects('close:', 'not a valid stop closure')
    rejects('close:CAS:BRK', 'not a valid stop closure')
    rejects('remove:ALP', 'not a link between two stops')
    rejects('remove:ALP-BRK-CAS', 'not a link between two stops')
    rejects('time:ALP-BRK', 'not a valid travel time change')
    rejects('close:%E0%A4', 'not a valid stop closure')
  })

  it('numbers that are not plain minutes', () => {
    for (const minutes of ['abc', '-3', '1e3', 'Infinity', '0x10', '']) {
      rejects(`time:ALP-BRK:${minutes}`, 'is not a number of minutes')
    }
  })

  it('times out of range', () => {
    rejects('time:ALP-BRK:0', 'more than 0')
    rejects('time:ALP-BRK:601', 'at most 600')
    expect(decodeChanges('time:ALP-BRK:600', network).ok).toBe(true)
  })

  it('unknown stops and links that do not exist', () => {
    rejects('close:XYZ', 'unknown stop "XYZ"')
    rejects('remove:ALP-CAS', 'no direct link from ALP to CAS')
  })

  it('frequency changes for unknown routes or out of range', () => {
    rejects('freq:R9:5', 'unknown route "R9"')
    rejects('freq:R1:0.5', 'every 1 to 120 minutes')
    rejects('freq:R1:121', 'every 1 to 120 minutes')
    rejects('freq:R1', 'not a valid frequency change')
    rejects('freq:R1:5:oneway', 'not a valid frequency change')
    rejects('freq:R1:fast', 'is not a number of minutes')
    expect(decodeChanges('freq:R1:120', network).ok).toBe(true)
  })

  it('more than 20 changes', () => {
    rejects(Array(21).fill('close:CAS').join('~'), '21 changes')
    expect(decodeChanges(Array(20).fill('close:CAS').join('~'), network).ok).toBe(true)
  })

  it('the whole link when one change is bad, naming that change', () => {
    expect(decodeChanges('close:CAS~close:XYZ~close:BRK', network)).toEqual({
      ok: false,
      error: 'change 2: unknown stop "XYZ"',
    })
  })

  it('nothing for an empty value', () => {
    expect(decodeChanges('', network)).toEqual({ ok: true, changes: [] })
  })
})
