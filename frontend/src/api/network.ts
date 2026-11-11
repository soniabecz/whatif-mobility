import type { Network } from '../types/network'
import { apiClient } from './client'

export async function fetchNetwork(): Promise<Network> {
  const response = await apiClient.get<Network>('/api/network')
  return response.data
}
