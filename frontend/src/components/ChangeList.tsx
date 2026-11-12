import { useEffect, useMemo, useState } from 'react'
import { Check, Info, Link2, ListChecks, Trash2, TriangleAlert, X } from 'lucide-react'

import { describeChange, stopsById } from '../lib/network'
import { sharePath } from '../lib/shareLink'
import type { Network } from '../types/network'
import { MAX_CHANGES, type ScenarioChange } from '../types/scenario'
import { CHANGE_ICONS } from './impactIcons'
import { Badge } from './ui/Badge'
import { Button } from './ui/Button'
import { IconButton } from './ui/IconButton'
import { SectionTitle } from './ui/SectionTitle'

/** Message about the list itself, e.g. the result of opening a shared link. */
export interface ListNotice {
  tone: 'info' | 'error'
  text: string
}

interface ChangeListProps {
  network: Network
  changes: ScenarioChange[]
  onChangesChange: (changes: ScenarioChange[]) => void
  disabled: boolean
  notice: ListNotice | null
  onDismissNotice: () => void
}

type CopyState = 'idle' | 'copied' | 'failed'

export function ChangeList({
  network,
  changes,
  onChangesChange,
  disabled,
  notice,
  onDismissNotice,
}: ChangeListProps) {
  const stops = useMemo(() => stopsById(network), [network])
  const [copyState, setCopyState] = useState<CopyState>('idle')

  // Reset the "Copied" / "Copy failed" label after a moment.
  useEffect(() => {
    if (copyState === 'idle') return
    const timer = window.setTimeout(() => setCopyState('idle'), 2000)
    return () => window.clearTimeout(timer)
  }, [copyState])

  async function copyLink() {
    const url = `${window.location.origin}${sharePath(window.location.pathname, changes)}`
    try {
      // Throws (or is missing) without permission or outside a secure context.
      await navigator.clipboard.writeText(url)
      setCopyState('copied')
    } catch {
      setCopyState('failed')
    }
  }

  return (
    <section className="space-y-3">
      <SectionTitle
        icon={ListChecks}
        aside={
          <div className="flex items-center gap-1">
            <Badge tone={changes.length > 0 ? 'accent' : 'neutral'}>
              {changes.length}/{MAX_CHANGES}
            </Badge>
            {changes.length > 0 && (
              <Button
                variant="ghost"
                size="sm"
                icon={copyState === 'copied' ? Check : Link2}
                onClick={copyLink}
                title={
                  copyState === 'failed'
                    ? 'The browser blocked the clipboard: copy the address bar instead'
                    : 'Copy a link to this list of changes'
                }
              >
                {copyState === 'copied' ? 'Copied' : copyState === 'failed' ? 'Copy failed' : 'Copy link'}
              </Button>
            )}
            {changes.length > 0 && (
              <Button
                variant="ghost"
                size="sm"
                icon={Trash2}
                onClick={() => onChangesChange([])}
                disabled={disabled}
              >
                Clear
              </Button>
            )}
          </div>
        }
      >
        Scenario
      </SectionTitle>

      {notice && (
        <div
          role={notice.tone === 'error' ? 'alert' : 'status'}
          className={
            notice.tone === 'error'
              ? 'flex items-start gap-2 rounded-xl bg-red-50 py-2 pr-1.5 pl-3 text-xs text-red-800'
              : 'flex items-start gap-2 rounded-xl bg-accent-soft py-2 pr-1.5 pl-3 text-xs text-ink'
          }
        >
          {notice.tone === 'error' ? (
            <TriangleAlert size={14} className="mt-0.5 shrink-0" aria-hidden />
          ) : (
            <Info size={14} className="mt-0.5 shrink-0 text-accent" aria-hidden />
          )}
          <p className="flex-1">{notice.text}</p>
          <IconButton icon={X} label="Dismiss" onClick={onDismissNotice} className="-my-1.5" />
        </div>
      )}

      {changes.length === 0 ? (
        <p className="rounded-xl border border-dashed border-line px-3 py-4 text-center text-xs text-ink-subtle">
          No changes yet. Describe one above or build it below.
        </p>
      ) : (
        <ol className="space-y-1.5">
          {changes.map((change, index) => {
            const Icon = CHANGE_ICONS[change.type]
            return (
              <li
                key={index}
                className="group flex items-center gap-2.5 rounded-xl border border-line bg-white py-1.5 pr-1.5 pl-2 text-sm shadow-xs"
              >
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-accent">
                  <Icon size={14} aria-hidden />
                </span>
                <span className="min-w-0 flex-1 text-ink">{describeChange(change, stops)}</span>
                <IconButton
                  icon={X}
                  label={`Remove change ${index + 1}`}
                  onClick={() => onChangesChange(changes.filter((_, i) => i !== index))}
                  disabled={disabled}
                  className="lg:opacity-0 lg:group-hover:opacity-100 lg:focus-visible:opacity-100"
                />
              </li>
            )
          })}
        </ol>
      )}
    </section>
  )
}
