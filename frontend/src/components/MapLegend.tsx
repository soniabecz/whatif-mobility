import { useState } from 'react'
import { ChevronDown, ChevronUp, Layers, Search } from 'lucide-react'

import { IMPACT_ORDER, IMPACT_STYLES, type ImpactLevel } from '../lib/impact'
import { LEGEND_FILTER_FROM, filterRoutes, scenarioHighlights } from '../lib/network'
import type { NetworkSource, Route } from '../types/network'
import type { ScenarioChange } from '../types/scenario'
import { IMPACT_ICONS } from './impactIcons'
import { Card } from './ui/Card'
import { cx } from './ui/cx'

interface MapLegendProps {
  /** Routes of the scenario network: the baseline's plus any the scenario adds. */
  routes: Route[]
  /** The scenario being built: changed frequencies and new routes are shown per route. */
  changes: ScenarioChange[]
  /** Results are shown: explain every stop colour. */
  showImpact: boolean
  /** A scenario is being built: explain the preview marks. */
  showScenario: boolean
  /** A journey is drawn by the explorer. */
  showJourney: boolean
  defaultOpen: boolean
  className?: string
  /** The network's data source (credited as its terms require); null only for test data. */
  source: NetworkSource | null
}

function weekday(isoDate: string): string {
  const day = new Date(`${isoDate}T12:00:00Z`)
  return Number.isNaN(day.getTime()) ? '' : day.toLocaleDateString('en-GB', { weekday: 'long', timeZone: 'UTC' })
}

export function MapLegend({
  routes,
  changes,
  showImpact,
  showScenario,
  showJourney,
  defaultOpen,
  className,
  source,
}: MapLegendProps) {
  const [open, setOpen] = useState(defaultOpen)
  const [query, setQuery] = useState('')
  const highlights = scenarioHighlights(changes)
  const newHeadways = highlights.headways
  const newRouteIds = new Set(highlights.addedRoutes.map((route) => route.route_id))
  const levels: ImpactLevel[] = showImpact ? IMPACT_ORDER : showScenario ? ['closed'] : []
  const sorted = [...routes].sort((a, b) => a.id.localeCompare(b.id, undefined, { numeric: true }))
  // Big networks (Gdańsk: 93 lines) get a filter box; the list scrolls in any case.
  const filterable = routes.length > LEGEND_FILTER_FROM
  const shown = filterable ? filterRoutes(sorted, query) : sorted

  return (
    // The caller limits the height (max-h); only the line list scrolls, so the
    // explanations and the data credit below it stay visible.
    <Card className={cx('flex w-72 flex-col text-xs', className)}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex w-full shrink-0 items-center justify-between gap-2 rounded-panel px-3 py-2.5 font-semibold text-ink focus-visible:ring-2 focus-visible:ring-accent-ring focus-visible:outline-none"
      >
        <span className="flex items-center gap-2">
          <Layers size={14} className="text-accent" aria-hidden />
          Legend
        </span>
        {open ? <ChevronUp size={14} aria-hidden /> : <ChevronDown size={14} aria-hidden />}
      </button>

      {open && (
        <div className="flex min-h-0 flex-col gap-3 border-t border-line px-3 pt-2.5 pb-3 text-ink-muted [&>*]:shrink-0">
          {filterable && (
            <label className="flex items-center gap-1.5 rounded-md border border-line bg-white px-2 py-1 focus-within:ring-2 focus-within:ring-accent-ring">
              <Search size={12} className="text-ink-subtle" aria-hidden />
              <input
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder={`Filter ${routes.length} lines`}
                aria-label="Filter lines"
                className="min-w-0 flex-1 bg-transparent text-ink outline-none placeholder:text-ink-subtle"
              />
            </label>
          )}
          {/* A long list keeps at least a few rows when the legend is squeezed; a short
              one keeps its natural height (a short legend must not grow). */}
          <ul
            className={cx('space-y-1.5 overflow-y-auto overscroll-contain shrink!', filterable && 'min-h-24 pr-1')}
            aria-label="Lines"
          >
            {filterable && shown.length === 0 && <li className="text-ink-subtle">No line matches “{query.trim()}”.</li>}
            {shown.map((route) => (
              <li key={route.id} className="flex items-center gap-2 whitespace-nowrap">
                {newRouteIds.has(route.id) ? (
                  <span className="w-6 shrink-0 border-t-[3px] border-dashed" style={{ borderColor: route.color }} />
                ) : (
                  <span
                    className="h-1.5 w-6 shrink-0 rounded-full ring-2 ring-white"
                    style={{ backgroundColor: route.color }}
                  />
                )}
                <span className="min-w-0 truncate">
                  <span className="font-semibold text-ink">{route.id}</span> {route.name}
                </span>
                {newRouteIds.has(route.id) && (
                  <span className="rounded bg-accent/10 px-1 text-[10px] font-semibold text-accent">new</span>
                )}
                {newHeadways.has(route.id) ? (
                  <span className="ml-auto pl-3 text-[11px] font-semibold text-accent tabular-nums">
                    every <s className="font-normal text-ink-subtle">{route.headway_min}</s>{' '}
                    {newHeadways.get(route.id)} min
                  </span>
                ) : (
                  <span className="ml-auto pl-3 text-[11px] text-ink-subtle tabular-nums">
                    every {route.headway_min} min
                  </span>
                )}
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
                <span className="w-6 border-t-[3px] border-dashed border-slate-900" /> Walking
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
                <li className="flex items-center gap-2">
                  <span className="w-6 border-t-[3px] border-dashed border-orange-500" /> Added link (route colour)
                </li>
                <li className="flex items-center gap-2">
                  <span className="ml-1.5 h-3.5 w-3.5 rounded-full border-4 border-orange-500 bg-white" />
                  <span className="ml-1">New stop</span>
                </li>
              </ul>
            </>
          )}

          {source ? (
            <div className="space-y-1 border-t border-line pt-2.5 text-[11px] leading-relaxed">
              <p>
                <span className="font-semibold text-ink">Timetable:</span>{' '}
                {source.attribution_url.startsWith('http') ? (
                  <a href={source.attribution_url} target="_blank" rel="noreferrer" className="text-accent underline">
                    {source.publisher}
                  </a>
                ) : (
                  source.publisher
                )}
              </p>
              <p>
                Data of {source.feed_created}, downloaded {source.downloaded}; network of{' '}
                {weekday(source.reference_date)} {source.reference_date}.
              </p>
              {source.licence && <p>{source.licence}</p>}
              <details>
                <summary className="cursor-pointer text-ink">How the network was built</summary>
                <p className="mt-1">{source.method}</p>
              </details>
            </div>
          ) : null}
        </div>
      )}
    </Card>
  )
}
