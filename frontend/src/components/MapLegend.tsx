import { IMPACT_ORDER, IMPACT_STYLES, type ImpactLevel } from '../lib/impact'
import type { Route } from '../types/network'

interface MapLegendProps {
  routes: Route[]
  /** Results are shown: explain every stop colour. */
  showImpact: boolean
  /** A scenario is being built: explain the preview marks. */
  showScenario: boolean
}

export function MapLegend({ routes, showImpact, showScenario }: MapLegendProps) {
  const levels: ImpactLevel[] = showImpact ? IMPACT_ORDER : showScenario ? ['closed'] : []

  return (
    // z-[1000]: above Leaflet's panes (which use z-index 400–700).
    <div className="absolute right-3 bottom-6 z-[1000] rounded-lg border border-slate-200 bg-white/95 p-3 text-xs text-slate-700 shadow-sm">
      <p className="mb-1 font-semibold text-slate-500 uppercase">Routes</p>
      <ul className="space-y-1">
        {routes.map((route) => (
          <li key={route.id} className="flex items-center gap-2">
            <span className="h-1.5 w-5 rounded-full" style={{ backgroundColor: route.color }} />
            {route.id} {route.name}
          </li>
        ))}
      </ul>

      {levels.length > 0 && (
        <>
          <p className="mt-3 mb-1 font-semibold text-slate-500 uppercase">Scenario</p>
          <ul className="space-y-1">
            {levels.map((level) => (
              <li key={level} className="flex items-center gap-2">
                <span
                  className="h-3 w-3 rounded-full border-2 border-white shadow"
                  style={{ backgroundColor: IMPACT_STYLES[level].color }}
                />
                {IMPACT_STYLES[level].icon} {IMPACT_STYLES[level].label}
              </li>
            ))}
          </ul>
          <p className="mt-2 flex items-center gap-2">
            <span className="w-5 border-t-2 border-dashed border-zinc-500" /> Removed link
          </p>
          <p className="mt-1 flex items-center gap-2">
            <span className="h-2 w-5 rounded-full bg-zinc-500" /> Travel time changed (thick)
          </p>
        </>
      )}
    </div>
  )
}
