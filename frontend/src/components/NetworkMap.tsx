import { useMemo } from 'react'
import { CircleMarker, MapContainer, Polyline, TileLayer, Tooltip } from 'react-leaflet'
import type { LatLngBoundsExpression } from 'leaflet'

import { IMPACT_STYLES, describeImpact, impactLevel } from '../lib/impact'
import { linkKey, routeSegments, scenarioHighlights } from '../lib/network'
import type { Network } from '../types/network'
import type { ScenarioChange } from '../types/scenario'
import type { SimulationResult, StopImpact } from '../types/simulation'
import { MapLegend } from './MapLegend'

interface NetworkMapProps {
  network: Network
  /** The scenario being built; previewed on the map before it is run. */
  changes: ScenarioChange[]
  result: SimulationResult | null
}

export function NetworkMap({ network, changes, result }: NetworkMapProps) {
  const segments = useMemo(() => routeSegments(network), [network])
  const routes = useMemo(
    () => new Map(network.routes.map((route) => [route.id, route])),
    [network],
  )
  const bounds = useMemo<LatLngBoundsExpression>(
    () => network.stops.map((stop) => [stop.lat, stop.lon] as [number, number]),
    [network],
  )
  const highlights = useMemo(() => scenarioHighlights(changes), [changes])
  const impacts = useMemo(
    () => new Map<string, StopImpact>(result?.stop_impacts.map((i) => [i.stop_id, i]) ?? []),
    [result],
  )

  return (
    <div className="relative h-full w-full">
      <MapContainer
        bounds={bounds}
        boundsOptions={{ padding: [40, 40] }}
        className="h-full w-full"
        scrollWheelZoom
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        {segments.map((segment) => {
          const route = routes.get(segment.routeId)
          const link = linkKey(segment.from.id, segment.to.id)
          const removed = highlights.removedLinks.has(link)
          const retimed = highlights.retimedLinks.has(link)
          return (
            <Polyline
              key={segment.key}
              positions={[
                [segment.from.lat, segment.from.lon],
                [segment.to.lat, segment.to.lon],
              ]}
              pathOptions={{
                color: removed ? '#71717a' : (route?.color ?? '#71717a'),
                weight: retimed ? 9 : 5,
                // Fade routes once results are shown so stop impacts stand out.
                opacity: removed ? 0.9 : result ? 0.45 : 0.85,
                dashArray: removed ? '6 8' : undefined,
              }}
            >
              <Tooltip sticky>
                <strong>{route?.name ?? segment.routeId}</strong>
                <br />
                {segment.from.name} – {segment.to.name}: {segment.travelTimeMin} min
                {removed && <><br />Removed in this scenario</>}
                {retimed && <><br />Travel time changed in this scenario</>}
              </Tooltip>
            </Polyline>
          )
        })}

        {network.stops.map((stop) => {
          const impact = impacts.get(stop.id)
          // Before a run, preview closures from the scenario being built.
          const level = result
            ? impactLevel(impact)
            : highlights.closedStopIds.has(stop.id)
              ? 'closed'
              : null
          const style = level ? IMPACT_STYLES[level] : null
          return (
            <CircleMarker
              key={stop.id}
              center={[stop.lat, stop.lon]}
              radius={level && level !== 'unaffected' ? 9 : 7}
              pathOptions={{
                color: '#ffffff',
                weight: 2,
                fillColor: style?.color ?? '#27272a',
                fillOpacity: 1,
              }}
            >
              <Tooltip>
                <strong>{stop.name}</strong> ({stop.id})
                {style && (
                  <>
                    <br />
                    {style.icon} {result ? describeImpact(impact) : style.label}
                  </>
                )}
              </Tooltip>
            </CircleMarker>
          )
        })}
      </MapContainer>
      <MapLegend
        routes={network.routes}
        showImpact={result !== null}
        showScenario={changes.length > 0}
      />
    </div>
  )
}
