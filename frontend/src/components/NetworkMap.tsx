import { useMemo } from 'react'
import {
  CircleMarker,
  MapContainer,
  Polyline,
  TileLayer,
  Tooltip,
  ZoomControl,
} from 'react-leaflet'
import type { LatLngBoundsExpression, PointTuple } from 'leaflet'

import { IMPACT_STYLES, describeImpact, impactLevel } from '../lib/impact'
import { linkKey, routeSegments, scenarioHighlights } from '../lib/network'
import type { Network } from '../types/network'
import type { ScenarioChange } from '../types/scenario'
import type { SimulationResult, StopImpact } from '../types/simulation'

interface NetworkMapProps {
  network: Network
  /** The scenario being built; previewed on the map before it is run. */
  changes: ScenarioChange[]
  result: SimulationResult | null
  /** Space taken by floating panels, so the network is fitted beside them. */
  fitPadding: { topLeft: PointTuple; bottomRight: PointTuple }
}

const INK = '#0f172a'
const REMOVED = '#71717a'

export function NetworkMap({ network, changes, result, fitPadding }: NetworkMapProps) {
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
    // Initial bounds only: MapContainer ignores later prop changes, so the
    // padding is read once when the map is created.
    <MapContainer
      bounds={bounds}
      boundsOptions={{
        paddingTopLeft: fitPadding.topLeft,
        paddingBottomRight: fitPadding.bottomRight,
      }}
      className="map-muted h-full w-full"
      scrollWheelZoom
      zoomControl={false}
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <ZoomControl position="topright" />

      {/* White casing under every line: crisp edges on any background. */}
      {segments.map((segment) => (
        <Polyline
          key={`${segment.key}:casing`}
          positions={[
            [segment.from.lat, segment.from.lon],
            [segment.to.lat, segment.to.lon],
          ]}
          interactive={false}
          pathOptions={{
            color: '#ffffff',
            weight: highlights.retimedLinks.has(linkKey(segment.from.id, segment.to.id)) ? 13 : 9,
            opacity: result ? 0.6 : 0.9,
            lineCap: 'round',
          }}
        />
      ))}

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
              color: removed ? REMOVED : (route?.color ?? REMOVED),
              weight: retimed ? 9 : 5,
              // Fade routes once results are shown so stop impacts stand out.
              opacity: removed ? 0.9 : result ? 0.5 : 0.95,
              dashArray: removed ? '2 10' : undefined,
              lineCap: 'round',
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
        const highlighted = level !== null && level !== 'unaffected'
        return (
          <CircleMarker
            key={stop.id}
            center={[stop.lat, stop.lon]}
            radius={highlighted ? 9 : 6}
            // Normal stops: white with a dark ring. Highlighted: status colour, white ring.
            pathOptions={{
              color: highlighted ? '#ffffff' : INK,
              weight: highlighted ? 3 : 2.5,
              fillColor: style?.color ?? '#ffffff',
              fillOpacity: 1,
            }}
          >
            <Tooltip direction="top" offset={[0, -8]}>
              <strong>{stop.name}</strong> <span style={{ color: '#8b95a5' }}>{stop.id}</span>
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
  )
}
