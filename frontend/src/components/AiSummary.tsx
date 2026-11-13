// "Summarise with AI" (Day 12): a short text about the computed results. The AI
// writes placeholders; the backend checks the text and inserts every number from
// its own simulation, so no figure here is written by the AI.

import { useState } from 'react'
import { CircleHelp, Sparkles, TriangleAlert } from 'lucide-react'

import { summariseResults } from '../api/ai'
import { describeApiError } from '../api/errors'
import type { SimulationResult } from '../types/simulation'
import { Badge } from './ui/Badge'
import { Button } from './ui/Button'

type State =
  | { kind: 'idle' }
  | { kind: 'loading'; result: SimulationResult }
  | { kind: 'ok'; result: SimulationResult; summary: string }
  | { kind: 'withheld'; result: SimulationResult; message: string }
  | { kind: 'error'; result: SimulationResult; message: string }

export function AiSummary({ result }: { result: SimulationResult }) {
  const [stored, setStored] = useState<State>({ kind: 'idle' })
  // A summary belongs to one result: a newer result (or a late answer for an
  // older one) shows the button again.
  const state: State = stored.kind !== 'idle' && stored.result === result ? stored : { kind: 'idle' }

  async function summarise() {
    setStored({ kind: 'loading', result })
    try {
      const response = await summariseResults(result.scenario.changes)
      setStored(
        response.status === 'ok' && response.summary
          ? { kind: 'ok', result, summary: response.summary }
          : { kind: 'withheld', result, message: response.message },
      )
    } catch (error: unknown) {
      setStored({ kind: 'error', result, message: describeApiError(error) })
    }
  }

  if (state.kind === 'idle' || state.kind === 'loading') {
    return (
      <Button
        size="sm"
        variant="secondary"
        icon={Sparkles}
        loading={state.kind === 'loading'}
        onClick={() => void summarise()}
        className="w-full"
      >
        {state.kind === 'loading' ? 'Summarising…' : 'Summarise with AI'}
      </Button>
    )
  }

  if (state.kind === 'ok') {
    return (
      <figure className="space-y-1.5 rounded-xl border border-accent/20 bg-accent/5 px-3 py-2.5">
        <figcaption className="flex items-center gap-2 text-xs font-semibold text-ink">
          <Sparkles size={13} className="text-accent" aria-hidden />
          AI summary
          <Badge tone="accent">AI</Badge>
        </figcaption>
        <p className="text-sm leading-relaxed text-ink">{state.summary}</p>
        <p className="text-[11px] leading-relaxed text-ink-subtle">
          Written by AI from the computed results. Every number was inserted from them, not
          written by the AI; check that the wording matches the figures below.
        </p>
      </figure>
    )
  }

  const Icon = state.kind === 'withheld' ? CircleHelp : TriangleAlert
  return (
    <div
      role={state.kind === 'error' ? 'alert' : 'status'}
      className={
        state.kind === 'withheld'
          ? 'flex gap-2 rounded-xl bg-amber-50 px-3 py-2 text-sm text-amber-900'
          : 'flex gap-2 rounded-xl bg-red-50 px-3 py-2 text-sm text-red-800'
      }
    >
      <Icon size={16} className="mt-0.5 shrink-0" aria-hidden />
      <span className="min-w-0 flex-1">{state.message}</span>
      <Button size="sm" variant="ghost" className="-my-1 shrink-0" onClick={() => void summarise()}>
        Try again
      </Button>
    </div>
  )
}
