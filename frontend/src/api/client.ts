import axios from 'axios'

// Vite exposes env variables prefixed with VITE_ to the browser code.
// Override in frontend/.env.local if the backend runs elsewhere.
const API_BASE_URL: string =
  import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

// One shared Axios instance, so base URL and timeout are configured once.
export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 5000,
})
