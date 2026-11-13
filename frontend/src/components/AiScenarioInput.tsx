import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import axios from 'axios'
import {
  CircleCheck,
  CircleHelp,
  Info,
  SendHorizontal,
  Sparkles,
  TriangleAlert,
  Undo2,
  type LucideIcon,
} from 'lucide-react'

import { interpretText } from '../api/ai'
import { describeApiError } from '../api/errors'
import { describeAiEdit, isStale } from '../lib/aiEdit'
import { MAX_AI_REQUEST_CHARS } from '../types/ai'
import type { ScenarioChange } from '../types/scenario'
import { Badge } from './ui/Badge'
import { Button } from './ui/Button'
import { IconButton } from './ui/IconButton'
import { SectionTitle } from './ui/SectionTitle'
import { cx } from './ui/cx'

interface AiScenarioInputProps {
  /** The current change list: sent with the request, so the AI can edit it. */
  changes: ScenarioChange[]
  /** Replaces the whole list (the AI's result, or the previous list on Undo). */
  onChangesChange: (changes: ScenarioChange[]) => void
  disabled: boolean
}

type Feedback =
  | { kind: 'none' }
  /** `applied` is the list the AI produced; Undo restores `previous` while it is unchanged. */
  | { kind: 'applied'; message: string; summary: string; previous: ScenarioChange[]; applied: ScenarioChange[] }
  | { kind: 'info'; message: string }
  | { kind: 'unclear'; message: string }
  | { kind: 'not-configured'; message: string }
  | { kind: 'error'; message: string }

const PLACEHOLDER = 'e.g. "Roadworks make Riverside – East Gate twice as slow"'

const FEEDBACK_STYLES: Record<
  Exclude<Feedback['kind'], 'none'>,
  { icon: LucideIcon; className: string }
> = {
  applied: { icon: CircleCheck, className: 'bg-green-50 text-green-800' },
  info: { icon: Info, className: 'bg-surface-muted text-ink-muted' },
  unclear: { icon: CircleHelp, className: 'bg-amber-50 text-amber-900' },
  'not-configured': { icon: Info, className: 'bg-surface-muted text-ink-muted' },
  error: { icon: TriangleAlert, className: 'bg-red-50 text-red-800' },
}

export function AiScenarioInput({ changes, onChangesChange, disabled }: AiScenarioInputProps) {
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [feedback, setFeedback] = useState<Feedback>({ kind: 'none' })
  // The list as it is now, read after the AI answers (the request's closure holds the old one).
  const latestChanges = useRef(changes)
  useEffect(() => {
    latestChanges.current = changes
  }, [changes])

  const canSubmit = !busy && !disabled && text.trim() !== ''

  async function submit() {
    const trimmed = text.trim()
    if (!trimmed) return
    setBusy(true)
    setFeedback({ kind: 'none' })
    const sent = changes
    try {
      const result = await interpretText(trimmed, sent)
      if (isStale(sent, latestChanges.current)) {
        setFeedback({
          kind: 'info',
          message: 'The list changed while the AI was thinking, so its answer was not applied. Please try again.',
        })
      } else if (result.status === 'ok') {
        onChangesChange(result.changes)
        setFeedback({
          kind: 'applied',
          message: result.message,
          summary: describeAiEdit(result),
          previous: sent,
          applied: result.changes,
        })
        setText('')
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
          <span className="min-w-0 flex-1">
            {feedback.kind === 'applied' && <strong className="font-semibold">{feedback.summary}. </strong>}
            {feedback.message}
          </span>
          {/* Undo only while the list is still exactly what the AI made of it. */}
          {feedback.kind === 'applied' && feedback.applied === changes && (
            <Button
              size="sm"
              variant="ghost"
              icon={Undo2}
              className="-my-1 shrink-0 text-green-800 hover:bg-green-100 hover:text-green-900"
              onClick={() => {
                onChangesChange(feedback.previous)
                setFeedback({ kind: 'info', message: 'Undone: the list is back as it was.' })
              }}
              disabled={disabled}
            >
              Undo
            </Button>
          )}
        </p>
      )}

      <p className="text-[11px] leading-relaxed text-ink-subtle">
        The AI only fills in the scenario below. Check it, then run the simulation:
        all results are calculated by the simulation, never by the AI.
      </p>
    </section>
  )
}
