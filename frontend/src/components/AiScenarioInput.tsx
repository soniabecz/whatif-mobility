import { useState, type FormEvent, type KeyboardEvent } from 'react'
import axios from 'axios'
import {
  CircleCheck,
  CircleHelp,
  Info,
  SendHorizontal,
  Sparkles,
  TriangleAlert,
  type LucideIcon,
} from 'lucide-react'

import { interpretText } from '../api/ai'
import { describeApiError } from '../api/errors'
import { MAX_AI_REQUEST_CHARS } from '../types/ai'
import type { ScenarioChange } from '../types/scenario'
import { Badge } from './ui/Badge'
import { IconButton } from './ui/IconButton'
import { SectionTitle } from './ui/SectionTitle'
import { cx } from './ui/cx'

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

const FEEDBACK_STYLES: Record<
  Exclude<Feedback['kind'], 'none'>,
  { icon: LucideIcon; className: string }
> = {
  added: { icon: CircleCheck, className: 'bg-green-50 text-green-800' },
  unclear: { icon: CircleHelp, className: 'bg-amber-50 text-amber-900' },
  'not-configured': { icon: Info, className: 'bg-surface-muted text-ink-muted' },
  error: { icon: TriangleAlert, className: 'bg-red-50 text-red-800' },
}

export function AiScenarioInput({ onAddChanges, disabled }: AiScenarioInputProps) {
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [feedback, setFeedback] = useState<Feedback>({ kind: 'none' })

  const canSubmit = !busy && !disabled && text.trim() !== ''

  async function submit() {
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

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    void submit()
  }

  // Enter sends, Shift+Enter adds a new line (chat convention).
  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      if (canSubmit) void submit()
    }
  }

  const style = feedback.kind === 'none' ? null : FEEDBACK_STYLES[feedback.kind]

  return (
    <section className="space-y-3">
      <SectionTitle icon={Sparkles} aside={<Badge tone="accent">AI</Badge>}>
        Describe a change
      </SectionTitle>

      <form
        onSubmit={handleSubmit}
        className={cx(
          'rounded-2xl border border-line bg-white p-2 shadow-sm transition-shadow',
          'focus-within:border-accent focus-within:ring-2 focus-within:ring-accent-ring/50',
        )}
      >
        <textarea
          aria-label="Describe a change in plain language"
          className="block w-full resize-none bg-transparent px-1.5 py-1 text-sm text-ink placeholder:text-ink-subtle focus:outline-none disabled:opacity-50"
          rows={2}
          maxLength={MAX_AI_REQUEST_CHARS}
          placeholder={PLACEHOLDER}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={busy || disabled}
        />
        <div className="flex items-center justify-between gap-2 pl-1.5">
          <span className="text-[11px] text-ink-subtle tabular-nums">
            {busy ? 'Interpreting…' : `${text.length}/${MAX_AI_REQUEST_CHARS}`}
          </span>
          <IconButton
            type="submit"
            icon={SendHorizontal}
            label="Interpret"
            tone="accent"
            disabled={!canSubmit}
            className={busy ? 'animate-pulse' : undefined}
          />
        </div>
      </form>

      {feedback.kind !== 'none' && style && (
        <p
          role={feedback.kind === 'error' ? 'alert' : 'status'}
          className={cx('flex gap-2 rounded-xl px-3 py-2 text-sm', style.className)}
        >
          <style.icon size={16} className="mt-0.5 shrink-0" aria-hidden />
          <span>
            {feedback.message}
            {feedback.kind === 'added' && feedback.added < feedback.total &&
              ` Only ${feedback.added} of ${feedback.total} changes fitted (limit reached).`}
          </span>
        </p>
      )}

      <p className="text-[11px] leading-relaxed text-ink-subtle">
        The AI only fills in the scenario below. Check it, then run the simulation:
        all results are calculated by the simulation, never by the AI.
      </p>
    </section>
  )
}
