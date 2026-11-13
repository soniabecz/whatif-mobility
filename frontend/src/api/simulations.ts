import type { Scenario } from '../types/scenario'
import type { SimulationResult } from '../types/simulation'
import { apiClient } from './client'

export async function runSimulation(scenario: Scenario): Promise<SimulationResult> {
  const response = await apiClient.post<SimulationResult>('/api/simulations', scenario)
  return response.data
}

/** Every changed journey as CSV text (a result lists only the largest changes). */
export async function fetchChangedJourneysCsv(scenario: Scenario): Promise<string> {
  const response = await apiClient.post<string>('/api/simulations/csv', scenario, { responseType: 'text' })
  return response.data
}
