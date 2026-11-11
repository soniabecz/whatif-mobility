// Mirrors backend/app/schemas/journey.py

import type { ScenarioChange } from './scenario'

export interface JourneyRequest {
  origin_id: string
  destination_id: string
  changes: ScenarioChange[]
}

/** A stretch on one route without changing bus. */
export interface JourneyLeg {
  route_id: string
  /** Every stop passed, in order, including closed stops the bus drives through. */
  stop_ids: string[]
  travel_time_min: number
  passes_closed_stop_ids: string[]
}

export interface JourneyPlan {
  travel_time_min: number
  legs: JourneyLeg[]
}

export type JourneyComparisonStatus = 'unchanged' | 'slower' | 'faster' | 'impossible' | 'unreachable'

export interface JourneyComparison {
  origin_id: string
  destination_id: string
  before: JourneyPlan | null
  after: JourneyPlan | null
  status: JourneyComparisonStatus
  change_min: number | null
  reason: string | null
}
