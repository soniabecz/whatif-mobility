import type { ReactNode } from 'react'

import { cx } from './cx'

type Tone = 'neutral' | 'accent' | 'success' | 'danger'

const TONES: Record<Tone, { badge: string; dot: string }> = {
  neutral: { badge: 'bg-surface-muted text-ink-muted', dot: 'bg-ink-subtle' },
  accent: { badge: 'bg-accent-soft text-accent', dot: 'bg-accent' },
  success: { badge: 'bg-green-50 text-green-700', dot: 'bg-green-600' },
  danger: { badge: 'bg-red-50 text-red-700', dot: 'bg-red-600' },
}

interface BadgeProps {
  tone?: Tone
  dot?: boolean
  pulse?: boolean
  children: ReactNode
}

export function Badge({ tone = 'neutral', dot = false, pulse = false, children }: BadgeProps) {
  return (
    <span
      className={cx(
        'inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-semibold',
        TONES[tone].badge,
      )}
    >
      {dot && (
        <span
          className={cx('h-1.5 w-1.5 rounded-full', TONES[tone].dot, pulse && 'animate-pulse')}
          aria-hidden
        />
      )}
      {children}
    </span>
  )
}
