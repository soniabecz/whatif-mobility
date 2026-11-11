// Mirrors backend/app/schemas/scenario.py

export interface CloseStop {
  type: 'close_stop'
  stop_id: string
}

export interface RemoveConnection {
  type: 'remove_connection'
  from_stop_id: string
  to_stop_id: string
  both_directions: boolean
}

export interface ChangeTravelTime {
  type: 'change_travel_time'
  from_stop_id: string
  to_stop_id: string
  travel_time_min: number
  both_directions: boolean
}

export type ScenarioChange = CloseStop | RemoveConnection | ChangeTravelTime

export type ChangeType = ScenarioChange['type']

/** Changes are applied in order. The backend accepts 1–20 changes. */
export interface Scenario {
  changes: ScenarioChange[]
}

export const MAX_CHANGES = 20
export const MAX_TRAVEL_TIME_MIN = 600
