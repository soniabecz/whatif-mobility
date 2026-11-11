import { useState, type FormEvent } from 'react'
import axios from 'axios'

import { interpretText } from '../api/ai'
import { describeApiError } from '../api/errors'
import { MAX_AI_REQUEST_CHARS } from '../types/ai'
import type { ScenarioChange } from '../types/scenario'

interface AiScenarioInputProps {
  /** Adds the interpreted changes to the list; returns how many fitted. */
  onAddChanges: (changes: ScenarioChange[]) => number
  disabled: boolean
}

type Feedback =
  | { kind: 'none' }
  | { kind: 'added'; message: string; added: number; total: number }
  | { kind: 'unclear'; message: string }
  | { kind: 'not-configured'; message: string }
  | { kind: 'error'; message: string }

const PLACEHOLDER = 'e.g. "Roadworks make Riverside – East Gate twice as slow"'

export function AiScenarioInput({ onAddChanges, disabled }: AiScenarioInputProps) {
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [feedback, setFeedback] = useState<Feedback>({ kind: 'none' })

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const trimmed = text.trim()
    if (!trimmed) return
    setBusy(true)
    setFeedback({ kind: 'none' })
    try {
      const result = await interpretText(trimmed)
      if (result.status === 'ok') {
        const added = onAddChanges(result.changes)
        setFeedback({ kind: 'added', message: result.message, added, total: result.changes.length })
        if (added > 0) setText('')
      } else {
        setFeedback({ kind: 'unclear', message: result.message })
      }
    } catch (error: unknown) {
      const notConfigured = axios.isAxiosError(error) && error.response?.status === 503
        && String(error.response.data?.detail ?? '').includes('not configured')
      setFeedback({
        kind: notConfigured ? 'not-configured' : 'error',
        message: describeApiError(error),
      })
    } finally {
      setBusy(false)
    }
  }

  return (
    <section>
      <h2 className="text-sm font-semibold tracking-wide text-slate-500 uppercase">
        Describe a change (AI)
      </h2>
      <form onSubmit={handleSubmit} className="mt-3 space-y-2">
        <textarea
          className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:outline-none"
          rows={2}
          maxLength={MAX_AI_REQUEST_CHARS}
          placeholder={PLACEHOLDER}
          value={text}
          onChange={(e) => setText(e.target.value)}
          disabled={busy || disabled}
        />
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs text-slate-400">
            {text.length}/{MAX_AI_REQUEST_CHARS}
          </span>
          <button
            type="submit"
            disabled={busy || disabled || text.trim() === ''}
            className="rounded-md border border-blue-600 px-3 py-1.5 text-sm font-medium text-blue-700 hover:bg-blue-50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy ? 'Interpreting…' : 'Interpret'}
          </button>
        </div>
      </form>
      <p className="mt-1 text-xs text-slate-500">
        The AI only fills in the list of changes below. Check them, then run the
        simulation; all results are calculated by the simulation, not the AI.
      </p>

      {feedback.kind === 'added' && (
        <p className="mt-2 rounded-md bg-green-50 p-2 text-sm text-green-800">
          ✓ {feedback.message}
          {feedback.added < feedback.total &&
            ` Only ${feedback.added} of ${feedback.total} changes fitted (limit reached).`}
        </p>
      )}
      {feedback.kind === 'unclear' && (
        <p className="mt-2 rounded-md bg-amber-50 p-2 text-sm text-amber-900">? {feedback.message}</p>
      )}
      {feedback.kind === 'not-configured' && (
        <p className="mt-2 rounded-md bg-slate-100 p-2 text-sm text-slate-700">ⓘ {feedback.message}</p>
      )}
      {feedback.kind === 'error' && (
        <p role="alert" className="mt-2 rounded-md bg-red-50 p-2 text-sm text-red-800">
          ❌ {feedback.message}
        </p>
      )}
    </section>
  )
}
