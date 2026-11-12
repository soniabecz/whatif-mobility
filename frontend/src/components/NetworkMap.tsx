import { useEffect, useMemo } from 'react'
import {
  CircleMarker,
  MapContainer,
  Marker,
  Pane,
  Polyline,
  TileLayer,
  Tooltip,
  ZoomControl,
  useMap,
} from 'react-leaflet'
import { divIcon, type LatLngBoundsExpression, type LatLngTuple, type PointTuple } from 'leaflet'

import type { DraftSelection } from '../lib/changeDraft'
import { ACTIVITY_LABELS, IMPACT_STYLES, describeImpact, impactLevel } from '../lib/impact'
import { linkKey, routeSegments, scenarioHighlights } from '../lib/network'
import type { JourneyComparison, JourneyLeg } from '../types/journey'
import type { Network, Route, Stop } from '../types/network'
import type { ScenarioChange } from '../types/scenario'
import type { SimulationResult, StopImpact } from '../types/simulation'

interface NetworkMapProps {
  network: Network
  /** The scenario being built; previewed on the map before it is run. */
  changes: ScenarioChange[]
  result: SimulationResult | null
  /** Space taken by floating panels, so the network is fitted beside them. */
  fitPadding: MapPadding
  /** Selected journey (explorer); drawn on top and zoomed to. */
  journey: JourneyComparison | null
  /** Free map area while a journey is shown (results card is open then). */
  journeyPadding: MapPadding
  /** Clicking stops and lines fills in the scenario form; null = clicks ignored. */
  mapSelect: MapSelect | null
}

export interface MapSelect {
  /** What the form currently points at; ringed on the map. */
  selection: DraftSelection
  onStopClick: (stopId: string) => void
  /** A line is one route's segment, so the route is known too. */
  onLinkClick: (fromId: string, toId: string, routeId: string) => void
}

export interface MapPadding {
  topLeft: PointTuple
  bottomRight: PointTuple
}

const INK = '#0f172a'
const REMOVED = '#71717a'
const SELECTED = '#4f46e5' // --color-accent

export function NetworkMap({
  network,
  changes,
  result,
  fitPadding,
  journey,
  journeyPadding,
  mapSelect,
}: NetworkMapProps) {
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
  const stopMap = useMemo(() => new Map(network.stops.map((s) => [s.id, s])), [network])
  // Fade the network further while a journey is shown.
  const lineOpacity = journey ? 0.18 : result ? 0.5 : 0.95
  const impacts = useMemo(
    () => new Map<string, StopImpact>(result?.stop_impacts.map((i) => [i.stop_id, i]) ?? []),
    [result],
  )
  // The form's selection is hidden while a journey is shown (it would compete with it).
  const selection = journey ? null : (mapSelect?.selection ?? null)
  const selectedStops = network.stops.filter((stop) => selection?.stopIds.includes(stop.id))
  const clickHint = mapSelect && <><br /><em style={{ color: '#8b95a5' }}>Click to select</em></>
  // Handlers read the latest mapSelect; react-leaflet rebinds them when they change.
  const linkClick = (from: string, to: string, routeId: string) => ({
    click: () => mapSelect?.onLinkClick(from, to, routeId),
  })

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

      {/* The form's selection (halo + rings) lives in its own pane BELOW the lines
          and stops. Leaflet stacks shapes in the order they are added, so without
          the pane a selection made later would cover the bus lines. */}
      <Pane name="selection" style={{ zIndex: 390 }}>
        {/* Indigo halo around the link (or, for "frequency", the whole route)
            selected in the form. */}
        {selection &&
          segments
            .filter((segment) =>
              selection.routeId !== null
                ? segment.routeId === selection.routeId
                : linkKey(segment.from.id, segment.to.id) === selection.link,
            )
            .map((segment) => (
              <Polyline
                key={`${segment.key}:selected`}
                positions={[
                  [segment.from.lat, segment.from.lon],
                  [segment.to.lat, segment.to.lon],
                ]}
                interactive={false}
                pathOptions={{ color: SELECTED, weight: 19, opacity: 0.6, lineCap: 'round' }}
              />
            ))}

        {/* Indigo ring around the stop(s) selected in the form. */}
        {selectedStops.map((stop) => (
          <CircleMarker
            key={`${stop.id}:selected`}
            center={[stop.lat, stop.lon]}
            radius={14}
            interactive={false}
            pathOptions={{ color: SELECTED, weight: 3, fillColor: SELECTED, fillOpacity: 0.15 }}
          />
        ))}
      </Pane>

      {/* White casing under every line: crisp edges on any background. It is
          wider than the line, so it is also the easier click target. */}
      {segments.map((segment) => (
        <Polyline
          key={`${segment.key}:casing`}
          positions={[
            [segment.from.lat, segment.from.lon],
            [segment.to.lat, segment.to.lon],
          ]}
          eventHandlers={linkClick(segment.from.id, segment.to.id, segment.routeId)}
          pathOptions={{
            className: `link-hit link-${segment.from.id}-${segment.to.id}`,
            color: '#ffffff',
            weight: highlights.retimedLinks.has(linkKey(segment.from.id, segment.to.id)) ? 13 : 9,
            opacity: journey ? 0.3 : result ? 0.6 : 0.9,
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
            eventHandlers={linkClick(segment.from.id, segment.to.id, segment.routeId)}
            pathOptions={{
              className: `route-line route-${segment.routeId} link-${segment.from.id}-${segment.to.id}`,
              color: removed ? REMOVED : (route?.color ?? REMOVED),
              weight: retimed ? 9 : 5,
              // Fade routes once results are shown so stop impacts stand out.
              opacity: removed && !journey ? 0.9 : lineOpacity,
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
              {clickHint}
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
            eventHandlers={{ click: () => mapSelect?.onStopClick(stop.id) }}
            // Normal stops: white with a dark ring. Highlighted: status colour, white ring.
            pathOptions={{
              className: `stop-marker stop-${stop.id}`,
              color: highlighted ? '#ffffff' : INK,
              weight: highlighted ? 3 : 2.5,
              fillColor: style?.color ?? '#ffffff',
              fillOpacity: 1,
            }}
          >
            <Tooltip direction="top" offset={[0, -8]}>
              <strong>{stop.name}</strong> <span style={{ color: '#8b95a5' }}>{stop.id}</span>
              <br />
              <span style={{ color: '#8b95a5' }}>
                Activity: {ACTIVITY_LABELS[stop.activity] ?? stop.activity} (invented)
              </span>
              {style && (
                <>
                  <br />
                  {style.icon} {result ? describeImpact(impact) : style.label}
                </>
              )}
              {clickHint}
            </Tooltip>
          </CircleMarker>
        )
      })}

      {journey && (
        <JourneyOverlay
          journey={journey}
          stops={stopMap}
          routes={routes}
          padding={journeyPadding}
        />
      )}
    </MapContainer>
  )
}

const BEFORE_COLOR = '#475569'

function pin(label: string) {
  return divIcon({
    className: '', // replaces Leaflet's default white box
    html: `<div class="journey-pin">${label}</div>`,
    iconSize: [26, 26],
    iconAnchor: [13, 13],
  })
}
const PIN_A = pin('A')
const PIN_B = pin('B')

function positions(stops: Map<string, Stop>, ids: string[]): LatLngTuple[] {
  return ids.flatMap((id) => {
    const stop = stops.get(id)
    return stop ? [[stop.lat, stop.lon] as LatLngTuple] : []
  })
}

/** All stops of a journey in order (legs share their transfer stop). */
function pathOf(legs: JourneyLeg[] | undefined): string[] {
  return (legs ?? []).flatMap((leg, index) => (index === 0 ? leg.stop_ids : leg.stop_ids.slice(1)))
}

function JourneyOverlay({
  journey,
  stops,
  routes,
  padding,
}: {
  journey: JourneyComparison
  stops: Map<string, Stop>
  routes: Map<string, Route>
  padding: MapPadding
}) {
  const map = useMap()
  const beforePath = positions(stops, pathOf(journey.before?.legs))
  const origin = stops.get(journey.origin_id)
  const destination = stops.get(journey.destination_id)

  // Zoom smoothly to the journey when it (or the free map area) changes.
  // The parent passes a stable padding object, so this does not run on every render.
  useEffect(() => {
    const points = positions(stops, [
      ...pathOf(journey.before?.legs),
      ...pathOf(journey.after?.legs),
    ])
    if (points.length > 0) {
      map.flyToBounds(points, {
        paddingTopLeft: padding.topLeft,
        paddingBottomRight: padding.bottomRight,
        maxZoom: 16,
        duration: 0.6,
      })
    }
  }, [map, journey, stops, padding])

  return (
    <>
      {beforePath.length > 1 && (
        <Polyline
          positions={beforePath}
          interactive={false}
          pathOptions={{ color: BEFORE_COLOR, weight: 4, dashArray: '1 9', lineCap: 'round' }}
        />
      )}
      {journey.after?.legs.map((leg, index) => (
        <Polyline
          key={`casing-${index}`}
          positions={positions(stops, leg.stop_ids)}
          interactive={false}
          pathOptions={{ color: '#ffffff', weight: 13, lineCap: 'round', lineJoin: 'round' }}
        />
      ))}
      {journey.after?.legs.map((leg, index) => (
        <Polyline
          key={`leg-${index}`}
          positions={positions(stops, leg.stop_ids)}
          pathOptions={{
            color: routes.get(leg.route_id)?.color ?? '#71717a',
            weight: 7,
            lineCap: 'round',
            lineJoin: 'round',
          }}
        >
          <Tooltip sticky>
            <strong>{routes.get(leg.route_id)?.name ?? leg.route_id}</strong>
            <br />
            {leg.travel_time_min.toFixed(1)} min on this route
          </Tooltip>
        </Polyline>
      ))}
      {origin && <Marker position={[origin.lat, origin.lon]} icon={PIN_A} title={`Start: ${origin.name}`} />}
      {destination && (
        <Marker
          position={[destination.lat, destination.lon]}
          icon={PIN_B}
          title={`Destination: ${destination.name}`}
        />
      )}
    </>
  )
}
