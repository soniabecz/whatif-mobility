// Aliases for types generated from the backend's OpenAPI schema
// (backend/app/schemas/ai.py). Regenerate with `npm run gen:types`.

import type { components } from './api.gen'

type Schemas = components['schemas']

// A value, not a type: keep in sync with backend/app/schemas/ai.py.
export const MAX_AI_REQUEST_CHARS = 500

export type InterpretRequest = Schemas['InterpretRequest']

/** 'ok': `changes` is the complete new list (valid for the network). 'unclear': nothing changes; see message. */
export type InterpretResponse = Schemas['InterpretResponse']
