// "Saved scenarios" (Day 13): load or delete a saved change list, and pick two
// scenarios (the current list may be one) to compare. Only change lists are
// saved; results are always recomputed.

import { useState } from 'react'
import { Columns2, FolderOpen, Loader2, Trash2, TriangleAlert } from 'lucide-react'

import type { SavedScenarioInfo } from '../types/saved'
import { Badge } from './ui/Badge'
import { Button } from './ui/Button'
import { Field, inputClass } from './ui/Field'
import { SectionTitle } from './ui/SectionTitle'

export type SavedListState =
  | { kind: 'loading' }
  | { kind: 'ready'; scenarios: SavedScenarioInfo[] }
  | { kind: 'error'; message: string }

/** "current" = the list being built; a number = a saved scenario's id. */
export type CompareChoice = 'current' | number

interface SavedScenariosProps {
  state: SavedListState
  hasCurrent: boolean
  onLoad: (scenario: SavedScenarioInfo) => void
  onDelete: (scenario: SavedScenarioInfo) => void
  onCompare: (a: CompareChoice, b: CompareChoice) => void
  comparing: boolean
  compareError: string | null
  disabled: boolean
}

const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' })

export function SavedScenarios({
  state,
  hasCurrent,
  onLoad,
  onDelete,
  onCompare,
  comparing,
  compareError,
  disabled,
}: SavedScenariosProps) {
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null)
  const [pickA, setPickA] = useState<string>('')
  const [pickB, setPickB] = useState<string>('')

  const scenarios = state.kind === 'ready' ? state.scenarios : []
  const fitting = scenarios.filter((s) => s.fits)
  const options: { value: string; label: string }[] = [
    ...(hasCurrent ? [{ value: 'current', label: 'Current list' }] : []),
    ...fitting.map((s) => ({ value: String(s.id), label: s.name })),
  ]
  const valid = (value: string) => options.some((option) => option.value === value)
  // Defaults: the current list against the newest saved scenario.
  const a = valid(pickA) ? pickA : (options[0]?.value ?? '')
  const b = valid(pickB) && pickB !== a ? pickB : (options.find((o) => o.value !== a)?.value ?? '')
  const toChoice = (value: string): CompareChoice => (value === 'current' ? 'current' : Number(value))

  return (
    <section className="space-y-3">
      <SectionTitle
        icon={FolderOpen}
        aside={state.kind === 'ready' && <Badge>{scenarios.length}</Badge>}
      >
        Saved scenarios
      </SectionTitle>

      {state.kind === 'loading' && (
        <p className="flex items-center gap-2 text-xs text-ink-subtle">
          <Loader2 size={14} className="animate-spin" aria-hidden /> Loading saved scenarios…
        </p>
      )}
      {state.kind === 'error' && (
        <p role="alert" className="flex gap-2 rounded-xl bg-red-50 px-3 py-2 text-xs text-red-800">
          <TriangleAlert size={14} className="mt-0.5 shrink-0" aria-hidden />
          {state.message}
        </p>
      )}
      {state.kind === 'ready' && scenarios.length === 0 && (
        <p className="rounded-xl border border-dashed border-line px-3 py-4 text-center text-xs text-ink-subtle">
          Nothing saved yet. Use “Save” on the scenario above.
        </p>
      )}

      {scenarios.length > 0 && (
        <ul className="space-y-1.5" aria-label="Saved scenarios">
          {scenarios.map((scenario) => (
            <li key={scenario.id} className="rounded-xl border border-line bg-white px-3 py-2 text-sm shadow-xs">
              <div className="flex items-center gap-2">
                <div className="min-w-0 flex-1">
                  <p className="truncate font-semibold text-ink">{scenario.name}</p>
                  <p className="text-[11px] text-ink-subtle">
                    {scenario.change_count} {scenario.change_count === 1 ? 'change' : 'changes'} ·{' '}
                    {dateFormat.format(new Date(scenario.updated_at))}
                  </p>
                </div>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => onLoad(scenario)}
                  disabled={disabled || !scenario.fits}
                  aria-label={`Load ${scenario.name}`}
                >
                  Load
                </Button>
                {confirmDelete === scenario.id ? (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="text-red-700 hover:bg-red-50 hover:text-red-800"
                    onClick={() => {
                      setConfirmDelete(null)
                      onDelete(scenario)
                    }}
                    onBlur={() => setConfirmDelete(null)}
                    autoFocus
                    disabled={disabled}
                  >
                    Delete?
                  </Button>
                ) : (
                  <Button
                    size="sm"
                    variant="ghost"
                    icon={Trash2}
                    onClick={() => setConfirmDelete(scenario.id)}
                    aria-label={`Delete ${scenario.name}`}
                    disabled={disabled}
                  />
                )}
              </div>
              {!scenario.fits && (
                <p className="mt-1 text-[11px] text-amber-800">{scenario.problem}</p>
              )}
            </li>
          ))}
        </ul>
      )}

      {options.length >= 2 && (
        <div className="space-y-2 rounded-xl bg-surface-muted p-2.5">
          <div className="grid grid-cols-2 gap-2">
            {(
              [
                ['A', a, setPickA],
                ['B', b, setPickB],
              ] as const
            ).map(([label, value, setValue]) => (
              <Field key={label} label={`Compare ${label}`}>
                <select
                  className={inputClass}
                  value={value}
                  onChange={(e) => setValue(e.target.value)}
                  disabled={disabled || comparing}
                >
                  {options.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </Field>
            ))}
          </div>
          <Button
            icon={Columns2}
            className="w-full"
            loading={comparing}
            onClick={() => onCompare(toChoice(a), toChoice(b))}
            disabled={disabled || a === b || a === '' || b === ''}
          >
            {a === b ? 'Pick two different scenarios' : 'Compare A and B'}
          </Button>
          {compareError && (
            <p role="alert" className="text-[11px] text-red-700">
              The comparison failed: {compareError}
            </p>
          )}
        </div>
      )}
    </section>
  )
}
