import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'

interface SectionTitleProps {
  icon: LucideIcon
  children: ReactNode
  /** Optional content on the right (badge, button). */
  aside?: ReactNode
}

export function SectionTitle({ icon: Icon, children, aside }: SectionTitleProps) {
  return (
    <div className="flex items-center justify-between gap-2">
      <h2 className="flex items-center gap-2 text-sm font-semibold text-ink">
        <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-accent-soft text-accent">
          <Icon size={14} aria-hidden />
        </span>
        {children}
      </h2>
      {aside}
    </div>
  )
}
