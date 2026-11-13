import type { ComparisonResult, SavedScenario, SavedScenarioInfo } from '../types/saved'
import type { ScenarioChange } from '../types/scenario'
import { apiClient } from './client'

export async function listSaved(): Promise<SavedScenarioInfo[]> {
  return (await apiClient.get<SavedScenarioInfo[]>('/api/scenarios')).data
}

export async function getSaved(id: number): Promise<SavedScenario> {
  return (await apiClient.get<SavedScenario>(`/api/scenarios/${id}`)).data
}

export async function saveScenario(name: string, changes: ScenarioChange[]): Promise<SavedScenario> {
  return (await apiClient.post<SavedScenario>('/api/scenarios', { name, changes })).data
}

export async function overwriteScenario(
  id: number,
  name: string,
  changes: ScenarioChange[],
): Promise<SavedScenario> {
  return (await apiClient.put<SavedScenario>(`/api/scenarios/${id}`, { name, changes })).data
}

export async function deleteSaved(id: number): Promise<void> {
  await apiClient.delete(`/api/scenarios/${id}`)
}

export async function compareScenarios(a: ScenarioChange[], b: ScenarioChange[]): Promise<ComparisonResult> {
  return (await apiClient.post<ComparisonResult>('/api/comparisons', { a, b })).data
}
