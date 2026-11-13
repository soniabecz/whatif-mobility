// Applying the AI's answer to the change list (Day 12). The backend already
// applied the AI's operations and validated the complete new list; here we only
// decide whether it may still replace the list and describe what it did.

import type { InterpretResponse } from '../types/ai'
import type { ScenarioChange } from '../types/scenario'

/**
 * The answer was computed for the list that was sent. If the user edited the
 * list while the AI was thinking, applying it would undo those edits.
 */
export function isStale(sent: ScenarioChange[], latest: ScenarioChange[]): boolean {
  return sent !== latest
}

/** "Removed 1 · changed 1 · added 2" (only the operations that happened). */
export function describeAiEdit(response: Pick<InterpretResponse, 'removed' | 'replaced' | 'added'>): string {
  const parts = [
    [response.removed?.length ?? 0, 'removed'],
    [response.replaced?.length ?? 0, 'changed'],
    [response.added ?? 0, 'added'],
  ] as const
  const text = parts
    .filter(([count]) => count > 0)
    .map(([count, verb]) => `${verb} ${count}`)
    .join(' · ')
  return text.charAt(0).toUpperCase() + text.slice(1)
}
