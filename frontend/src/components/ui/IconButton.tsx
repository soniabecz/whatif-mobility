import type { ButtonHTMLAttributes } from 'react'
import type { LucideIcon } from 'lucide-react'

import { cx } from './cx'

interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  icon: LucideIcon
  /** Required: the button has no visible text. */
  label: string
  tone?: 'neutral' | 'accent'
}

export function IconButton({
  icon: Icon,
  label,
  tone = 'neutral',
  className,
  type = 'button',
  ...props
}: IconButtonProps) {
  return (
    <button
      type={type}
      aria-label={label}
      title={label}
      className={cx(
        'inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-colors',
        'focus-visible:ring-2 focus-visible:ring-accent-ring focus-visible:outline-none',
        'disabled:cursor-not-allowed disabled:opacity-40',
        tone === 'accent'
          ? 'bg-accent text-white shadow-sm hover:bg-accent-hover'
          : 'text-ink-subtle hover:bg-surface-muted hover:text-ink',
        className,
      )}
      {...props}
    >
      <Icon size={16} aria-hidden />
    </button>
  )
}
