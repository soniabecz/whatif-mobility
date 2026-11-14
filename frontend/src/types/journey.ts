// Aliases for types generated from the backend's OpenAPI schema
// (backend/app/schemas/journey.py). Regenerate with `npm run gen:types`.

import type { components } from './api.gen'

type Schemas = components['schemas']

export type JourneyRequest = Schemas['JourneyRequest']

/** A stretch on one route without changing bus. */
export type JourneyLeg = Schemas['JourneyLeg']

/** A walk between two stops (distance estimated: straight line × 1.3); `before_leg` places it. */
export type WalkLeg = Schemas['WalkLeg']

/** travel_time_min = in_vehicle_min + transfers * transfer_penalty_min */
export type JourneyPlan = Schemas['JourneyPlan']

export type JourneyComparison = Schemas['JourneyComparison']
export type JourneyComparisonStatus = JourneyComparison['status']
