// Mirrors backend/app/schemas/ai.py

import type { ScenarioChange } from './scenario'

export const MAX_AI_REQUEST_CHARS = 500

export interface InterpretRequest {
  text: string
}

/** 'ok': changes are valid for the network. 'unclear': no changes; see message. */
export interface InterpretResponse {
  status: 'ok' | 'unclear'
  changes: ScenarioChange[]
  message: string
}
