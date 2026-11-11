import axios from 'axios'

/** One FastAPI/Pydantic validation problem (HTTP 422 with a list detail). */
interface ValidationIssue {
  loc?: (string | number)[]
  msg?: string
}

function describeDetail(detail: unknown): string | null {
  // Our own scenario errors: {"detail": "Change 1 (close_stop): unknown stop 'X'"}
  if (typeof detail === 'string') return detail
  // Pydantic schema errors: {"detail": [{"loc": [...], "msg": "..."}]}
  if (Array.isArray(detail)) {
    const messages = (detail as ValidationIssue[])
      .map((issue) => {
        const where = (issue.loc ?? []).filter((part) => part !== 'body').join(' → ')
        return issue.msg ? (where ? `${where}: ${issue.msg}` : issue.msg) : null
      })
      .filter((message): message is string => message !== null)
    if (messages.length > 0) return messages.join('; ')
  }
  return null
}

/** Turn any error from an API call into one readable sentence. */
export function describeApiError(error: unknown): string {
  if (axios.isAxiosError(error)) {
    if (error.response) {
      const data: unknown = error.response.data
      const detail =
        typeof data === 'object' && data !== null && 'detail' in data
          ? describeDetail(data.detail)
          : null
      return detail ?? `Backend responded with HTTP ${error.response.status}.`
    }
    if (error.code === 'ECONNABORTED') {
      return 'The backend took too long to respond. Please try again.'
    }
    return 'Could not reach the backend. Is it running on port 8000?'
  }
  return 'Unexpected error while contacting the backend.'
}
