// Two scenarios side by side (Day 13). Every number comes from the backend,
// which simulated both against today's network.

import { useEffect, useRef } from 'react'
import { Columns2, X } from 'lucide-react'

import { betterSide, comparisonRows, formatValue } from '../lib/comparison'
import { stopLabel } from '../lib/network'
import type { Stop } from '../types/network'
import type { ComparisonResult } from '../types/saved'
import { IconButton } from './ui/IconButton'
import { SectionTitle } from './ui/SectionTitle'
import { cx } from './ui/cx'

interface ComparisonPanelProps {
  result: ComparisonResult
  labelA: string
  labelB: string
  stops: Map<string, Stop>
  onClose: () => void
}

export function ComparisonPanel({ result, labelA, labelB, stops, onClose }: ComparisonPanelProps) {
  const section = useRef<HTMLElement>(null)
  // On a phone the panel opens at the top of the sheet, far above the Compare
  // button: bring it into view (on desktop it is already at the top of its card).
  useEffect(() => {
    section.current?.scrollIntoView({ block: 'start', behavior: 'smooth' })
  }, [result])
  const rows = comparisonRows(result.a, result.b)
  const name = (id: string) => stopLabel(stops, id)
  // Pairs side by side: A on the left, B on the right.
  const counts: [string, number][] = [
    ['Faster in A', result.a_faster],
    ['Faster in B', result.b_faster],
    ['Only possible in A', result.only_possible_in_a],
    ['Only possible in B', result.only_possible_in_b],
  ]

  return (
    <section ref={section} className="scroll-mt-2 space-y-3" aria-label="Comparison">
      <SectionTitle icon={Columns2} aside={<IconButton icon={X} label="Close comparison" onClick={onClose} />}>
        Compare
      </SectionTitle>

      <dl className="grid grid-cols-2 gap-2 text-xs">
        {(
          [
            ['A', labelA],
            ['B', labelB],
          ] as const
        ).map(([side, label]) => (
          <div key={side} className="rounded-xl bg-surface-muted px-3 py-2">
            <dt className="text-[11px] font-semibold text-ink-subtle">{side}</dt>
            <dd className="truncate font-semibold text-ink" title={label}>
              {label}
            </dd>
          </div>
        ))}
      </dl>

      <table className="w-full text-sm">
        <caption className="pb-1 text-left text-[11px] text-ink-subtle">
          Each side compared with today’s network. The better of A and B is highlighted.
        </caption>
        <thead>
          <tr className="text-[11px] text-ink-subtle">
            <th scope="col" className="py-1 text-left font-medium">
              Journeys
            </th>
            <th scope="col" className="py-1 text-right font-medium">
              A
            </th>
            <th scope="col" className="py-1 text-right font-medium">
              B
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line tabular-nums">
          {rows.map((row) => {
            const better = betterSide(row)
            return (
              <tr key={row.label}>
                <th scope="row" className="py-1.5 text-left font-normal text-ink-muted">
                  {row.label}
                </th>
                {(['a', 'b'] as const).map((side) => {
                  const was = side === 'a' ? row.wasA : row.wasB
                  return (
                    <td
                      key={side}
                      className={cx(
                        'py-1.5 text-right',
                        better === side ? 'font-semibold text-green-700' : 'text-ink',
                      )}
                      data-better={better === side || undefined}
                    >
                      {formatValue(row[side], row.unit)}
                      {was !== undefined && (
                        <span className="block text-[10px] font-normal text-ink-subtle">
                          was {formatValue(was, row.unit)}
                        </span>
                      )}
                    </td>
                  )
                })}
              </tr>
            )
          })}
        </tbody>
      </table>

      <div>
        <p className="text-xs font-semibold text-ink">
          A against B, journey by journey{' '}
          <span className="font-normal text-ink-subtle">({result.compared_journeys} journeys)</span>
        </p>
        <ul className="mt-1 grid grid-cols-2 gap-x-3 gap-y-0.5 text-xs text-ink-muted tabular-nums">
          <li className="col-span-2 flex justify-between gap-2">
            Same in both <span className="font-semibold text-ink">{result.same}</span>
          </li>
          {counts.map(([label, value]) => (
            <li key={label} className="flex justify-between gap-2">
              {label} <span className="font-semibold text-ink">{value}</span>
            </li>
          ))}
        </ul>
      </div>

      {result.largest_differences.length > 0 ? (
        <table className="w-full text-left text-sm">
          <caption className="pb-1 text-left text-xs font-semibold text-ink">
            Largest differences{' '}
            <span className="font-normal text-ink-subtle">(minutes; A − B positive = longer in A)</span>
          </caption>
          <thead>
            <tr className="text-[11px] text-ink-subtle">
              <th scope="col" className="py-1 font-medium">Journey</th>
              <th scope="col" className="py-1 text-right font-medium">A</th>
              <th scope="col" className="py-1 text-right font-medium">B</th>
              <th scope="col" className="py-1 text-right font-medium">A − B</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line tabular-nums">
            {result.largest_differences.map((d) => (
              <tr key={`${d.origin_id}-${d.destination_id}`}>
                <td className="py-1.5 pr-2 text-ink">
                  {name(d.origin_id)} → {name(d.destination_id)}
                </td>
                <td className="py-1.5 text-right">{d.time_a_min == null ? 'impossible' : d.time_a_min.toFixed(1)}</td>
                <td className="py-1.5 text-right">{d.time_b_min == null ? 'impossible' : d.time_b_min.toFixed(1)}</td>
                <td className="py-1.5 text-right font-semibold">
                  {d.difference_min == null ? '—' : `${d.difference_min > 0 ? '+' : ''}${d.difference_min.toFixed(1)}`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="text-xs text-ink-subtle">Every journey takes the same time in A and B.</p>
      )}
    </section>
  )
}
