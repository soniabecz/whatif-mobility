import { useEffect, useState } from 'react'
import axios from 'axios'
import { fetchHealth } from './api/health'

// The three states the connection check can be in.
// A "discriminated union": TypeScript knows `message` only exists on 'error'.
type ConnectionState =
  | { kind: 'loading' }
  | { kind: 'connected' }
  | { kind: 'error'; message: string }

function describeError(error: unknown): string {
  if (axios.isAxiosError(error)) {
    if (error.response) {
      return `Backend responded with HTTP ${error.response.status}.`
    }
    return 'Could not reach the backend. Is it running on port 8000?'
  }
  return 'Unexpected error while contacting the backend.'
}

function App() {
  const [connection, setConnection] = useState<ConnectionState>({
    kind: 'loading',
  })

  useEffect(() => {
    // Runs once after the first render. `ignore` prevents updating state
    // if the component is removed before the request finishes.
    let ignore = false

    fetchHealth()
      .then((data) => {
        if (ignore) return
        if (data.status === 'ok') {
          setConnection({ kind: 'connected' })
        } else {
          setConnection({
            kind: 'error',
            message: `Unexpected status: "${data.status}"`,
          })
        }
      })
      .catch((error: unknown) => {
        if (!ignore) setConnection({ kind: 'error', message: describeError(error) })
      })

    return () => {
      ignore = true
    }
  }, [])

  return (
    <main className="min-h-screen bg-slate-50 p-8 text-slate-800">
      <h1 className="text-3xl font-bold">WhatIf Mobility</h1>
      <p className="mt-2 text-slate-600">
        Simulate changes to a city bus network.
      </p>

      <section className="mt-8 max-w-md rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
          Backend status
        </h2>
        {connection.kind === 'loading' && (
          <p className="mt-2 text-slate-500">Checking connection…</p>
        )}
        {connection.kind === 'connected' && (
          <p className="mt-2 font-medium text-green-700">Backend connected ✅</p>
        )}
        {connection.kind === 'error' && (
          <p className="mt-2 font-medium text-red-700">
            ❌ {connection.message}
          </p>
        )}
      </section>
    </main>
  )
}

export default App
