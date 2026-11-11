import type { HTMLAttributes } from 'react'

import { cx } from './cx'

/** Floating, slightly translucent surface used for every panel over the map. */
export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cx(
        'rounded-panel border border-white/70 bg-white/90 shadow-panel backdrop-blur-xl',
        className,
      )}
      {...props}
    />
  )
}
