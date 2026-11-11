import { useEffect, useMemo, useRef, useState } from 'react'

import { describeApiError } from './api/errors'
import { fetchNetwork } from './api/network'
import { runSimulation } from './api/simulations'
import { NetworkMap } from './components/NetworkMap'
import { ResultsPanel } from './components/ResultsPanel'
import { ScenarioForm } from './components/ScenarioForm'
import { stopsById } from './lib/network'
import type { Network } from './types/network'
import type { ScenarioChange } from './types/scenario'
import type { SimulationResult } from './types/simulation'

// Discriminated unions: TypeScript knows which fields exist in each state.
type NetworkState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; network: Network }

type SimulationState =
  | { kind: 'idle' }
  | { kind: 'running' }
  | { kind: 'error'; message: string }
  | { kind: 'success'; result: SimulationResult }

function App() {
  const [networkState, setNetworkState] = useState<NetworkState>({ kind: 'loading' })
  const [reloadToken, setReloadToken] = useState(0)
  const [changes, setChanges] = useState<ScenarioChange[]>([])
  const [simulation, setSimulation] = useState<SimulationState>({ kind: 'idle' })
  // Incremented on every run and every edit, so a slow response for an
  // outdated scenario is ignored instead of overwriting newer state.
  const requestId = useRef(0)

  useEffect(() => {
    let ignore = false
    fetchNetwork()
      .then((network) => {
        if (ignore) return
        if (network.stops.length === 0) {
          setNetworkState({
            kind: 'error',
            message: 'The network is empty. Run "python -m app.seed" in backend/ and retry.',
          })
        } else {
          setNetworkState({ kind: 'ready', network })
        }
      })
      .catch((error: unknown) => {
        if (!ignore) setNetworkState({ kind: 'error', message: describeApiError(error) })
      })
    return () => {
      ignore = true
    }
  }, [reloadToken])

  function retryNetwork() {
    setNetworkState({ kind: 'loading' })
    setReloadToken((token) => token + 1)
  }

  function handleChangesChange(next: ScenarioChange[]) {
    requestId.current += 1
    setChanges(next)
    setSimulation({ kind: 'idle' }) // results always match the listed changes
  }

  async function handleRun() {
    const id = ++requestId.current
    setSimulation({ kind: 'running' })
    try {
      const result = await runSimulation({ changes })
      if (id === requestId.current) setSimulation({ kind: 'success', result })
    } catch (error: unknown) {
      if (id === requestId.current) {
        setSimulation({ kind: 'error', message: describeApiError(error) })
      }
    }
  }

  const stops = useMemo(
    () => (networkState.kind === 'ready' ? stopsById(networkState.network) : new Map()),
    [networkState],
  )
  const result = simulation.kind === 'success' ? simulation.result : null

  return (
    <div className="flex min-h-screen flex-col bg-slate-50 text-slate-800 lg:h-screen">
      <header className="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-3">
        <div>
          <h1 className="text-xl font-bold">WhatIf Mobility</h1>
          <p className="text-sm text-slate-500">Simulate changes to a city bus network.</p>
        </div>
        <ConnectionBadge state={networkState.kind} />
      </header>

      {networkState.kind === 'loading' && (
        <p className="p-8 text-slate-500">Loading the bus network…</p>
      )}

      {networkState.kind === 'error' && (
        <div className="m-8 max-w-lg rounded-lg border border-red-200 bg-white p-4" role="alert">
          <p className="font-medium text-red-700">❌ Could not load the bus network.</p>
          <p className="mt-1 text-sm text-slate-600">{networkState.message}</p>
          <button
            type="button"
            onClick={retryNetwork}
            className="mt-3 rounded-md bg-blue-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-blue-700"
          >
            Retry
          </button>
        </div>
      )}

      {networkState.kind === 'ready' && (
        <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
          <aside className="order-2 space-y-8 border-slate-200 bg-white p-4 lg:order-1 lg:w-[420px] lg:shrink-0 lg:overflow-y-auto lg:border-r">
            <ScenarioForm
              network={networkState.network}
              changes={changes}
              onChangesChange={handleChangesChange}
              onRun={handleRun}
              running={simulation.kind === 'running'}
              error={simulation.kind === 'error' ? simulation.message : null}
            />
            {result ? (
              <ResultsPanel result={result} stops={stops} />
            ) : (
              <p className="text-sm text-slate-500">
                Results appear here after you run a simulation.
              </p>
            )}
          </aside>
          <main className="order-1 h-[55vh] lg:order-2 lg:h-auto lg:flex-1">
            <NetworkMap network={networkState.network} changes={changes} result={result} />
          </main>
        </div>
      )}
    </div>
  )
}

function ConnectionBadge({ state }: { state: NetworkState['kind'] }) {
  const styles = {
    loading: { dot: 'bg-slate-400', text: 'Connecting…' },
    ready: { dot: 'bg-green-600', text: 'Connected' },
    error: { dot: 'bg-red-600', text: 'Offline' },
  }[state]
  return (
    <span className="flex items-center gap-2 text-sm text-slate-600">
      <span className={`h-2.5 w-2.5 rounded-full ${styles.dot}`} />
      {styles.text}
    </span>
  )
}

export default App
