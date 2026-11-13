import type { ReactNode } from 'react'

/** Look of a text/number/select input, without size or margin. */
export const inputBaseClass =
  'rounded-xl border border-line bg-white px-3 text-sm text-ink ' +
  'transition-colors hover:border-ink-subtle/60 ' +
  'focus:border-accent focus:ring-2 focus:ring-accent-ring/50 focus:outline-none ' +
  'disabled:cursor-not-allowed disabled:opacity-50'

/** A full-width input below its label. */
export const inputClass = `mt-1 h-10 w-full ${inputBaseClass}`

interface FieldProps {
  label: string
  hint?: ReactNode
  children: ReactNode
}

/** Label + control + optional hint. The control is nested, so no htmlFor is needed. */
export function Field({ label, hint, children }: FieldProps) {
  return (
    <label className="block text-xs font-semibold text-ink-muted">
      {label}
      {children}
      {hint && <span className="mt-1 block text-[11px] font-normal text-ink-subtle">{hint}</span>}
    </label>
  )
}
