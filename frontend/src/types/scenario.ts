// Aliases for types generated from the backend's OpenAPI schema
// (backend/app/schemas/scenario.py). Regenerate with `npm run gen:types`.

import type { components } from './api.gen'

type Schemas = components['schemas']

export type CloseStop = Schemas['CloseStop']
export type RemoveConnection = Schemas['RemoveConnection']
export type ChangeTravelTime = Schemas['ChangeTravelTime']

export type ScenarioChange = CloseStop | RemoveConnection | ChangeTravelTime

export type ChangeType = ScenarioChange['type']

/** Changes are applied in order. The backend accepts 1–20 changes. */
export type Scenario = Schemas['Scenario']

// Validation limits are values, not types, so OpenAPI cannot generate them.
// Keep in sync with backend/app/schemas/scenario.py.
export const MAX_CHANGES = 20
export const MAX_TRAVEL_TIME_MIN = 600
