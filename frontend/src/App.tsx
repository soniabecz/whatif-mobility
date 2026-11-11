import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { BusFront, ChevronDown, ChevronUp, Loader2, RotateCcw, TriangleAlert } from 'lucide-react'

import { describeApiError } from './api/errors'
import { fetchNetwork } from './api/network'
import { runSimulation } from './api/simulations'
import { AiScenarioInput } from './components/AiScenarioInput'
import { ChangeList } from './components/ChangeList'
import { MapLegend } from './components/MapLegend'
import { NetworkMap } from './components/NetworkMap'
import { ResultsPanel } from './components/ResultsPanel'
import { RunBar } from './components/RunBar'
import { ScenarioForm } from './components/ScenarioForm'
import { Badge } from './components/ui/Badge'
import { Button } from './components/ui/Button'
import { Card } from './components/ui/Card'
import { cx } from './components/ui/cx'
import { DESKTOP_QUERY, useMediaQuery } from './hooks/useMediaQuery'
import { stopsById } from './lib/network'
import type { Network } from './types/network'
import { MAX_CHANGES, type ScenarioChange } from './types/scenario'
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

// Map padding so the network is fitted beside the floating panels.
const DESKTOP_FIT = { topLeft: [460, 60] as [number, number], bottomRight: [60, 60] as [number, number] }
const MOBILE_FIT = { topLeft: [24, 64] as [number, number], bottomRight: [24, 120] as [number, number] }

function App() {
  const [networkState, setNetworkState] = useState<NetworkState>({ kind: 'loading' })
  const [reloadToken, setReloadToken] = useState(0)
  const [changes, setChanges] = useState<ScenarioChange[]>([])
  const [simulation, setSimulation] = useState<SimulationState>({ kind: 'idle' })
  const [sheetOpen, setSheetOpen] = useState(true)
  const isDesktop = useMediaQuery(DESKTOP_QUERY)
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

  /** Append AI-interpreted changes (up to the limit); returns how many fitted. */
  function handleAddChanges(added: ScenarioChange[]): number {
    const fitting = added.slice(0, Math.max(0, MAX_CHANGES - changes.length))
    if (fitting.length > 0) handleChangesChange([...changes, ...fitting])
    return fitting.length
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
  const running = simulation.kind === 'running'

  if (networkState.kind !== 'ready') {
    return <StatusScreen state={networkState} onRetry={retryNetwork} />
  }
  const { network } = networkState

  const scenarioSections = (
    <>
      <AiScenarioInput onAddChanges={handleAddChanges} disabled={running} />
      <ChangeList
        network={network}
        changes={changes}
        onChangesChange={handleChangesChange}
        disabled={running}
      />
      <ScenarioForm
        network={network}
        changeCount={changes.length}
        onAdd={(change) => handleChangesChange([...changes, change])}
        disabled={running}
      />
    </>
  )
  const runBar = (
    <RunBar
      changeCount={changes.length}
      running={running}
      error={simulation.kind === 'error' ? simulation.message : null}
      onRun={handleRun}
    />
  )

  return (
    <div className="relative h-dvh w-full overflow-hidden">
      <div className="absolute inset-0">
        <NetworkMap
          network={network}
          changes={changes}
          result={result}
          fitPadding={isDesktop ? DESKTOP_FIT : MOBILE_FIT}
        />
      </div>

      {/* Leaflet panes use z-index up to 1000, so overlays sit above that. */}
      <MapLegend
        key={isDesktop ? 'desktop' : 'mobile'}
        routes={network.routes}
        showImpact={result !== null}
        showScenario={changes.length > 0}
        defaultOpen={isDesktop}
        className="absolute top-3 left-3 z-[1100] lg:top-4 lg:left-[436px]"
      />

      {isDesktop ? (
        <>
          <Card className="absolute top-4 bottom-4 left-4 z-[1100] flex w-[404px] flex-col overflow-hidden">
            <PanelHeader status="live" />
            <div className="flex-1 space-y-7 overflow-y-auto px-5 pt-2 pb-5">{scenarioSections}</div>
            <div className="border-t border-line bg-white/70 p-4">{runBar}</div>
          </Card>

          {result && (
            <Card className="absolute right-2.5 bottom-7 z-[1100] max-h-[calc(100dvh-7rem)] w-[420px] overflow-y-auto p-4">
              <ResultsPanel result={result} stops={stops} />
            </Card>
          )}
        </>
      ) : (
        <Card
          className={cx(
            'absolute inset-x-0 bottom-0 z-[1100] flex flex-col overflow-hidden rounded-b-none',
            sheetOpen ? 'max-h-[72dvh]' : 'max-h-none',
          )}
        >
          <button
            type="button"
            onClick={() => setSheetOpen(!sheetOpen)}
            aria-expanded={sheetOpen}
            aria-label={sheetOpen ? 'Collapse panel' : 'Expand panel'}
            className="flex w-full flex-col items-center pt-2 focus-visible:outline-none"
          >
            <span className="h-1 w-10 rounded-full bg-ink-subtle/40" aria-hidden />
          </button>
          <PanelHeader
            status="live"
            aside={
              <Button
                variant="ghost"
                size="sm"
                icon={sheetOpen ? ChevronDown : ChevronUp}
                onClick={() => setSheetOpen(!sheetOpen)}
              >
                {sheetOpen ? 'Hide' : `Scenario (${changes.length})`}
              </Button>
            }
          />
          {sheetOpen && (
            <>
              <div className="flex-1 space-y-7 overflow-y-auto px-4 pt-2 pb-4">
                {result && <ResultsPanel result={result} stops={stops} />}
                {scenarioSections}
              </div>
              <div className="border-t border-line bg-white/70 p-3">{runBar}</div>
            </>
          )}
        </Card>
      )}
    </div>
  )
}

type ConnectionStatus = 'live' | 'connecting' | 'offline'

const CONNECTION_BADGES = {
  live: { tone: 'success', label: 'Live', pulse: true },
  connecting: { tone: 'neutral', label: 'Connecting…', pulse: true },
  offline: { tone: 'danger', label: 'Offline', pulse: false },
} as const

function PanelHeader({ status, aside }: { status: ConnectionStatus; aside?: ReactNode }) {
  const badge = CONNECTION_BADGES[status]
  return (
    <header className="flex items-center justify-between gap-3 px-5 pt-4 pb-3 max-lg:px-4 max-lg:pt-1">
      <div className="flex items-center gap-3">
        <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-linear-to-br from-indigo-500 to-violet-600 text-white shadow-soft">
          <BusFront size={20} aria-hidden />
        </span>
        <div>
          <h1 className="text-base leading-tight font-bold tracking-tight text-ink">
            WhatIf Mobility
          </h1>
          <p className="text-xs text-ink-subtle">What if the bus network changed?</p>
        </div>
      </div>
      {aside ?? (
        <Badge tone={badge.tone} dot pulse={badge.pulse}>
          {badge.label}
        </Badge>
      )}
    </header>
  )
}

function StatusScreen({
  state,
  onRetry,
}: {
  state: Exclude<NetworkState, { kind: 'ready' }>
  onRetry: () => void
}) {
  return (
    <div className="flex h-dvh items-center justify-center bg-linear-to-br from-slate-100 to-indigo-50 p-4">
      <Card className="w-full max-w-sm p-2">
        <PanelHeader status={state.kind === 'loading' ? 'connecting' : 'offline'} />
        <div className="px-5 pb-5">
          {state.kind === 'loading' ? (
            <p className="flex items-center gap-2 text-sm text-ink-muted">
              <Loader2 size={16} className="animate-spin text-accent" aria-hidden />
              Loading the bus network…
            </p>
          ) : (
            <div role="alert" className="space-y-3">
              <p className="flex gap-2 rounded-xl bg-red-50 px-3 py-2 text-sm text-red-800">
                <TriangleAlert size={16} className="mt-0.5 shrink-0" aria-hidden />
                <span>
                  <strong className="block">Could not load the bus network.</strong>
                  {state.message}
                </span>
              </p>
              <Button variant="primary" icon={RotateCcw} onClick={onRetry} className="w-full">
                Retry
              </Button>
            </div>
          )}
        </div>
      </Card>
    </div>
  )
}

export default App
