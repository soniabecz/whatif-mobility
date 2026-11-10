// TypeScript mirrors of the backend's Pydantic response models.
// Keep these in sync with backend/app/main.py (and later backend/app/schemas/).

export interface HealthResponse {
  status: string
}
