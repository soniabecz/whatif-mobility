import type { Scenario } from '../types/scenario'
import type { SimulationResult } from '../types/simulation'
import { apiClient } from './client'

export async function runSimulation(scenario: Scenario): Promise<SimulationResult> {
  const response = await apiClient.post<SimulationResult>('/api/simulations', scenario)
  return response.data
}
