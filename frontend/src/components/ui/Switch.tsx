import { cx } from './cx'

interface SwitchProps {
  label: string
  checked: boolean
  onChange: (checked: boolean) => void
  disabled: boolean
}

/** A labelled on/off switch (a checkbox with role "switch"). */
export function Switch({ label, checked, onChange, disabled }: SwitchProps) {
  return (
    <label
      className={cx(
        'flex items-center justify-between gap-3 rounded-xl bg-surface-muted px-3 py-2 text-sm text-ink',
        disabled ? 'cursor-not-allowed opacity-60' : 'cursor-pointer',
      )}
    >
      {label}
      <input
        type="checkbox"
        role="switch"
        className="peer sr-only"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        disabled={disabled}
      />
      <span
        aria-hidden
        className={cx(
          'relative h-5 w-9 shrink-0 rounded-full bg-ink-subtle/40 transition-colors',
          'peer-checked:bg-accent peer-focus-visible:ring-2 peer-focus-visible:ring-accent-ring',
          'after:absolute after:top-0.5 after:left-0.5 after:h-4 after:w-4 after:rounded-full',
          'after:bg-white after:shadow after:transition-transform peer-checked:after:translate-x-4',
        )}
      />
    </label>
  )
}
