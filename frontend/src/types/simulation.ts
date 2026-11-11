// Mirrors backend/app/schemas/simulation.py.
// Every number here is computed by the backend; the frontend only displays it.

import type { Scenario } from './scenario'

export type JourneyStatus = 'slower' | 'faster' | 'impossible'

export interface JourneyChange {
  origin_id: string
  destination_id: string
  time_before_min: number
  time_after_min: number | null // null = no longer possible
  change_min: number | null
  status: JourneyStatus
}

export interface SimulationSummary {
  total_journeys: number
  unchanged: number
  slower: number
  faster: number
  impossible: number
  to_or_from_closed_stop: number
  average_time_before_min: number | null
  average_time_after_min: number | null
  total_time_change_min: number
  largest_increase: JourneyChange | null
  /** Minutes counted per change of bus (backend setting). */
  transfer_penalty_min: number
}

export interface StopImpact {
  stop_id: string
  closed: boolean
  affected_journeys: number
  impossible_journeys: number
  average_change_min: number | null
}

export interface SimulationResult {
  scenario: Scenario
  summary: SimulationSummary
  changed_journeys: JourneyChange[]
  stop_impacts: StopImpact[]
  most_affected_stop_ids: string[]
}
