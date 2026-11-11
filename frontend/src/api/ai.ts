import type { InterpretRequest, InterpretResponse } from '../types/ai'
import { apiClient } from './client'

// The AI needs a few seconds; the backend itself gives up after 30 s.
const AI_TIMEOUT_MS = 60_000

export async function interpretText(text: string): Promise<InterpretResponse> {
  const body: InterpretRequest = { text }
  const response = await apiClient.post<InterpretResponse>('/api/ai/interpret', body, {
    timeout: AI_TIMEOUT_MS,
  })
  return response.data
}
