import { useMemo } from 'react'
import { ListChecks, Trash2, X } from 'lucide-react'

import { describeChange, stopsById } from '../lib/network'
import type { Network } from '../types/network'
import { MAX_CHANGES, type ScenarioChange } from '../types/scenario'
import { CHANGE_ICONS } from './impactIcons'
import { Badge } from './ui/Badge'
import { Button } from './ui/Button'
import { IconButton } from './ui/IconButton'
import { SectionTitle } from './ui/SectionTitle'

interface ChangeListProps {
  network: Network
  changes: ScenarioChange[]
  onChangesChange: (changes: ScenarioChange[]) => void
  disabled: boolean
}

export function ChangeList({ network, changes, onChangesChange, disabled }: ChangeListProps) {
  const stops = useMemo(() => stopsById(network), [network])

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
