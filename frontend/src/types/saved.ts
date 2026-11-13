// Aliases for types generated from the backend's OpenAPI schema
// (backend/app/schemas/saved_scenario.py). Regenerate with `npm run gen:types`.

import type { components } from './api.gen'

type Schemas = components['schemas']

/** A row of the saved list; `fits` = it applies to the current network. */
export type SavedScenarioInfo = Schemas['SavedScenarioInfo']
export type SavedScenario = Schemas['SavedScenarioOut']
/** Every number is computed by the backend from two fresh simulations. */
export type ComparisonResult = Schemas['ComparisonResult']
export type JourneyDifference = Schemas['JourneyDifference']
