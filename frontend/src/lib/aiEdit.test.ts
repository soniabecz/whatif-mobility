import { describe, expect, it } from 'vitest'

import type { ScenarioChange } from '../types/scenario'
import { describeAiEdit, isStale } from './aiEdit'

describe('describeAiEdit', () => {
  it('lists only the operations that happened', () => {
    expect(describeAiEdit({ removed: [2], replaced: [], added: 0 })).toBe('Removed 1')
    expect(describeAiEdit({ removed: [1, 3], replaced: [2], added: 2 })).toBe('Removed 2 · changed 1 · added 2')
    expect(describeAiEdit({ removed: [], replaced: [], added: 1 })).toBe('Added 1')
  })
})

describe('isStale', () => {
  const sent: ScenarioChange[] = [{ type: 'close_stop', stop_id: 'CAS' }]

  it('is fresh while the list is the one that was sent', () => {
    expect(isStale(sent, sent)).toBe(false)
  })

  it('is stale after any edit, even one that looks the same', () => {
    expect(isStale(sent, [...sent])).toBe(true)
    expect(isStale(sent, [])).toBe(true)
  })
})
