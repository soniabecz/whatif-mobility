import { useState } from 'react'
import { ChevronDown, ChevronUp, Layers } from 'lucide-react'

import { IMPACT_ORDER, IMPACT_STYLES, type ImpactLevel } from '../lib/impact'
import type { Route } from '../types/network'
import { IMPACT_ICONS } from './impactIcons'
import { Card } from './ui/Card'
import { cx } from './ui/cx'

interface MapLegendProps {
  routes: Route[]
  /** Results are shown: explain every stop colour. */
  showImpact: boolean
  /** A scenario is being built: explain the preview marks. */
  showScenario: boolean
  /** A journey is drawn by the explorer. */
  showJourney: boolean
  defaultOpen: boolean
  className?: string
}

export function MapLegend({
  routes,
  showImpact,
  showScenario,
  showJourney,
  defaultOpen,
  className,
}: MapLegendProps) {
  const [open, setOpen] = useState(defaultOpen)
  const levels: ImpactLevel[] = showImpact ? IMPACT_ORDER : showScenario ? ['closed'] : []

  return (
    <Card className={cx('w-56 text-xs', className)}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-2 rounded-panel px-3 py-2.5 font-semibold text-ink focus-visible:ring-2 focus-visible:ring-accent-ring focus-visible:outline-none"
      >
        <span className="flex items-center gap-2">
          <Layers size={14} className="text-accent" aria-hidden />
          Legend
        </span>
        {open ? <ChevronUp size={14} aria-hidden /> : <ChevronDown size={14} aria-hidden />}
      </button>

      {open && (
        <div className="space-y-3 border-t border-line px-3 pt-2.5 pb-3 text-ink-muted">
          <ul className="space-y-1.5">
            {routes.map((route) => (
              <li key={route.id} className="flex items-center gap-2">
                <span
                  className="h-1.5 w-6 rounded-full ring-2 ring-white"
                  style={{ backgroundColor: route.color }}
                />
                <span className="font-semibold text-ink">{route.id}</span> {route.name}
              </li>
            ))}
          </ul>

          {showJourney && (
            <ul className="space-y-1.5 border-t border-line pt-2.5">
              <li className="flex items-center gap-2">
                <span className="h-1.5 w-6 rounded-full bg-linear-to-r from-red-600 via-blue-600 to-orange-500" />
                Journey after (route colours)
              </li>
              <li className="flex items-center gap-2">
                <span className="w-6 border-t-[3px] border-dotted border-slate-600" /> Journey before
              </li>
              <li className="flex items-center gap-2">
                <span className="journey-pin scale-75">A</span>
                <span className="journey-pin -ml-3 scale-75">B</span>
                Start · destination
              </li>
            </ul>
          )}

          {levels.length > 0 && (
            <>
              <ul className="space-y-1.5 border-t border-line pt-2.5">
                {levels.map((level) => {
                  const Icon = IMPACT_ICONS[level]
                  return (
                    <li key={level} className="flex items-center gap-2">
                      <span
                        className="flex h-4 w-4 items-center justify-center rounded-full text-white ring-2 ring-white"
                        style={{ backgroundColor: IMPACT_STYLES[level].color }}
                      >
                        <Icon size={10} aria-hidden />
                      </span>
                      {IMPACT_STYLES[level].label}
                    </li>
                  )
                })}
              </ul>
              <ul className="space-y-1.5">
                <li className="flex items-center gap-2">
                  <span className="w-6 border-t-2 border-dashed border-zinc-500" /> Removed link
                </li>
                <li className="flex items-center gap-2">
                  <span className="h-2 w-6 rounded-full bg-zinc-500" /> Travel time changed
                </li>
              </ul>
            </>
          )}
        </div>
      )}
    </Card>
  )
}
