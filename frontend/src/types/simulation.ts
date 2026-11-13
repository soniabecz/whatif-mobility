// Aliases for types generated from the backend's OpenAPI schema
// (backend/app/schemas/simulation.py). Regenerate with `npm run gen:types`.
// Every number here is computed by the backend; the frontend only displays it.

import type { components } from './api.gen'

type Schemas = components['schemas']

export type JourneyChange = Schemas['JourneyChange']
export type JourneyStatus = JourneyChange['status']
export type SimulationSummary = Schemas['SimulationSummary']
export type StopImpact = Schemas['StopImpact']
export type SimulationResult = Schemas['SimulationResult']

/** A result lists at most this many changed journeys (backend MAX_CHANGED_JOURNEYS),
 *  plus the chart's; `changed_journeys_total` counts all, and the CSV has all. */
export const MAX_LISTED_JOURNEYS = 1000
