import type { LucideIcon } from 'lucide-react'

import { cx } from './cx'

export interface SegmentOption<T extends string> {
  value: T
  label: string
  icon: LucideIcon
}

interface SegmentedControlProps<T extends string> {
  label: string
  options: SegmentOption<T>[]
  value: T
  onChange: (value: T) => void
  disabled?: boolean
}

/** A row of mutually exclusive choices (radio group semantics). */
export function SegmentedControl<T extends string>({
  label,
  options,
  value,
  onChange,
  disabled = false,
}: SegmentedControlProps<T>) {
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className="grid gap-1 rounded-xl bg-surface-muted p-1"
      // More than four options: two rows of three, so labels stay on one line.
      style={{
        gridTemplateColumns: `repeat(${options.length > 4 ? 3 : options.length}, minmax(0, 1fr))`,
      }}
    >
      {options.map(({ value: optionValue, label: optionLabel, icon: Icon }) => {
        const active = optionValue === value
        return (
          <button
            key={optionValue}
            type="button"
            role="radio"
            aria-checked={active}
            disabled={disabled}
            onClick={() => onChange(optionValue)}
            className={cx(
              'flex flex-col items-center gap-1 rounded-lg px-1 py-2 text-[11px] font-semibold transition-all',
              'focus-visible:ring-2 focus-visible:ring-accent-ring focus-visible:outline-none',
              'disabled:cursor-not-allowed disabled:opacity-50',
              active
                ? 'bg-white text-accent shadow-sm'
                : 'text-ink-muted hover:bg-white/60 hover:text-ink',
            )}
          >
            <Icon size={16} aria-hidden />
            {optionLabel}
          </button>
        )
      })}
    </div>
  )
}
