import type { JourneyComparison, JourneyRequest } from '../types/journey'
import { apiClient } from './client'

export async function compareJourney(request: JourneyRequest): Promise<JourneyComparison> {
  const response = await apiClient.post<JourneyComparison>('/api/journeys', request)
  return response.data
}
