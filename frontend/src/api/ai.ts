import type { InterpretRequest, InterpretResponse } from '../types/ai'
import type { ScenarioChange } from '../types/scenario'
import { apiClient } from './client'

// The AI needs a few seconds; the backend itself gives up after 30 s.
const AI_TIMEOUT_MS = 60_000

/** Ask the AI to apply `text` to the current change list; 'ok' returns the complete new list. */
export async function interpretText(
  text: string,
  currentChanges: ScenarioChange[],
): Promise<InterpretResponse> {
  const body: InterpretRequest = { text, current_changes: currentChanges }
  const response = await apiClient.post<InterpretResponse>('/api/ai/interpret', body, {
    timeout: AI_TIMEOUT_MS,
  })
  return response.data
}
