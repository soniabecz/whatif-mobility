import type { HealthResponse } from '../types/api'
import { apiClient } from './client'

export async function fetchHealth(): Promise<HealthResponse> {
  const response = await apiClient.get<HealthResponse>('/api/health')
  return response.data
}
