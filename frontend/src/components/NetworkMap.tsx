import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react'
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
  useMapEvents,
} from 'react-leaflet'
import { divIcon, type LatLngBoundsExpression, type LatLngTuple, type PointTuple } from 'leaflet'

import type { DraftSelection } from '../lib/changeDraft'
import { IMPACT_STYLES, describeImpact, impactLevel } from '../lib/impact'
import {
  compactStops,
  linesOnStreet,
  linkKey,
  routeSegments,
  routeStretches,
  scenarioHighlights,
  stopMarkerSize,
  streetIndex,
  type StreetLine,
} from '../lib/network'
import { journeyStopIds } from '../lib/journeyPlan'
import type { JourneyComparison } from '../types/journey'
import type { Network, NetworkSource, Route, Stop } from '../types/network'
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
  /** A click anywhere on the map ("Add stop" places the new stop there). */
  onMapClick: (lat: number, lon: number) => void
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
  const streets = useMemo(() => streetIndex(network), [network])
  // Big networks: plain stops are small when zoomed out (set by CompactStopsWatcher).
  const [compact, setCompact] = useState(false)

  const bounds = useMemo<LatLngBoundsExpression>(
    () => network.stops.map((stop) => [stop.lat, stop.lon] as [number, number]),
    [network],
  )
  const highlights = useMemo(() => scenarioHighlights(changes), [changes])
  // Baseline routes plus routes the scenario adds (for colours and names everywhere).
  const addedRoutes = highlights.addedRoutes
  const routes = useMemo(() => {
    const map = new Map(network.routes.map((route) => [route.id, route]))
    for (const added of addedRoutes) {
      map.set(added.route_id, { id: added.route_id, name: added.name, color: added.color, headway_min: added.headway_min })
    }
    return map
  }, [network, addedRoutes])
  // Baseline stops plus stops the scenario adds (journeys may pass through them).
  const addedStops = highlights.addedStops
  const stopMap = useMemo(() => {
    const map = new Map(network.stops.map((s) => [s.id, s]))
    for (const added of addedStops) {
      map.set(added.stop_id, { id: added.stop_id, name: added.name, lat: added.lat, lon: added.lon, activity: 1 })
    }
    return map
  }, [network, addedStops])
  // Stretches of routes the scenario adds, one line per street (both directions share it).
  const addedRouteLines = useMemo(
    () =>
      addedRoutes.flatMap((added) =>
        routeStretches(added).map(([fromId, toId, minutes]) => ({
          key: `${added.route_id}:${linkKey(fromId, toId)}`,
          routeId: added.route_id,
          fromId,
          toId,
          minutes,
          bothDirections: added.both_directions,
        })),
      ),
    [addedRoutes],
  )
  // Fade the network further while a journey is shown.
  const lineOpacity = journey ? 0.18 : result ? 0.5 : 0.95
  const impacts = useMemo(
    () => new Map<string, StopImpact>(result?.stop_impacts.map((i) => [i.stop_id, i]) ?? []),
    [result],
  )
  // The form's selection is hidden while a journey is shown (it would compete with it).
  const selection = journey ? null : (mapSelect?.selection ?? null)
  const selectedStops = [...stopMap.values()].filter((stop) => selection?.stopIds.includes(stop.id))
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
        {selection?.routeId &&
          addedRouteLines
            .filter((line) => line.routeId === selection.routeId)
            .map((line) => (
              <Polyline
                key={`${line.key}:selected`}
                positions={positions(stopMap, [line.fromId, line.toId])}
                interactive={false}
                pathOptions={{ color: SELECTED, weight: 19, opacity: 0.6, lineCap: 'round' }}
              />
            ))}

        {/* "Add stop": dashed indigo marker where the new stop will go. */}
        {selection?.newStop && (
          <CircleMarker
            center={[selection.newStop.lat, selection.newStop.lon]}
            radius={9}
            interactive={false}
            pathOptions={{ color: SELECTED, weight: 3, dashArray: '3 3', fillColor: '#ffffff', fillOpacity: 1 }}
          />
        )}

        {/* "Add link": dashed indigo preview of the link being planned. */}
        {selection?.newLink && (
          <Polyline
            positions={positions(stopMap, [selection.newLink.fromId, selection.newLink.toId])}
            interactive={false}
            pathOptions={{ color: SELECTED, weight: 5, opacity: 0.8, dashArray: '6 8', lineCap: 'round' }}
          />
        )}

        {/* "Add route": dashed preview through the chosen stops, in the route's colour. */}
        {selection?.newRoute && selection.newRoute.stopIds.length > 1 && (
          <Polyline
            positions={positions(stopMap, [
              ...selection.newRoute.stopIds,
              ...(selection.newRoute.isLoop ? [selection.newRoute.stopIds[0]] : []),
            ])}
            interactive={false}
            pathOptions={{
              className: 'new-route-preview',
              color: selection.newRoute.color,
              weight: 6,
              opacity: 0.85,
              dashArray: '6 8',
              lineCap: 'round',
              lineJoin: 'round',
            }}
          />
        )}

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

      {/* Links added by the scenario: dashed, in the route's colour, on a white casing.
          Own pane below lines and stops: added later, they would otherwise cover the stops. */}
      <Pane name="added-links" style={{ zIndex: 395 }}>
        {highlights.addedLinks.map((added, index) => {
          const route = routes.get(added.routeId)
          const line = positions(stopMap, [added.fromId, added.toId])
          return (
            <Fragment key={`added-${index}`}>
              <Polyline
                positions={line}
                interactive={false}
                pathOptions={{ color: '#ffffff', weight: 9, opacity: journey ? 0.3 : 0.9, lineCap: 'round' }}
              />
              <Polyline
                positions={line}
                pathOptions={{
                  className: `added-link added-${added.fromId}-${added.toId}`,
                  color: route?.color ?? REMOVED,
                  weight: 5,
                  opacity: journey ? 0.3 : 0.95,
                  dashArray: '10 8',
                }}
              >
                <Tooltip sticky>
                  <strong>{route?.name ?? added.routeId}</strong> (added in this scenario)
                  <br />
                  {stopMap.get(added.fromId)?.name} {added.bothDirections ? '–' : '→'}{' '}
                  {stopMap.get(added.toId)?.name}: {added.travelTimeMin} min
                </Tooltip>
              </Polyline>
            </Fragment>
          )
        })}
        {/* Routes added by the scenario: dashed in their colour, clickable like other lines
            (so later changes such as a frequency or a new stop can pick them). */}
        {addedRouteLines.map((line) => {
          const route = routes.get(line.routeId)
          const points = positions(stopMap, [line.fromId, line.toId])
          return (
            <Fragment key={`added-route-${line.key}`}>
              <Polyline
                positions={points}
                eventHandlers={linkClick(line.fromId, line.toId, line.routeId)}
                pathOptions={{ color: '#ffffff', weight: 9, opacity: journey ? 0.3 : 0.9, lineCap: 'round' }}
              />
              <Polyline
                positions={points}
                eventHandlers={linkClick(line.fromId, line.toId, line.routeId)}
                pathOptions={{
                  className: `added-route route-${line.routeId} link-${line.fromId}-${line.toId}`,
                  color: route?.color ?? REMOVED,
                  weight: 5,
                  opacity: journey ? 0.3 : 0.95,
                  dashArray: '10 8',
                }}
              >
                <Tooltip sticky>
                  <strong>{route?.name ?? line.routeId}</strong> (new route in this scenario)
                  <br />
                  {stopMap.get(line.fromId)?.name} {line.bothDirections ? '–' : '→'}{' '}
                  {stopMap.get(line.toId)?.name}: {line.minutes} min
                  {clickHint}
                </Tooltip>
              </Polyline>
            </Fragment>
          )
        })}
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
              <StreetTooltip
                from={segment.from.name}
                to={segment.to.name}
                lines={linesOnStreet(streets, segment.from.id, segment.to.id)}
                underCursor={segment.routeId}
                routes={routes}
              />
              {removed && <><br />Removed in this scenario</>}
              {retimed && <><br />Travel time changed in this scenario</>}
              {mapSelect && (
                <>
                  <br />
                  <em style={{ color: '#8b95a5' }}>Click to select {route?.name ?? segment.routeId}</em>
                </>
              )}
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
        const size = stopMarkerSize(level, compact)
        return (
          <CircleMarker
            key={stop.id}
            center={[stop.lat, stop.lon]}
            radius={size.radius}
            eventHandlers={{ click: () => mapSelect?.onStopClick(stop.id) }}
            // Normal stops: white with a dark ring. Highlighted: status colour, white ring.
            pathOptions={{
              className: `stop-marker stop-${stop.id}`,
              color: highlighted ? '#ffffff' : INK,
              weight: size.weight,
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
              {clickHint}
            </Tooltip>
          </CircleMarker>
        )
      })}

      {/* Stops added by the scenario: their links dashed in the route colour (own pane,
          below the stops), and a white marker with a thick route-coloured ring. */}
      <Pane name="added-stop-links" style={{ zIndex: 396 }}>
        {addedStops.flatMap((added) =>
          [added.from_stop_id, added.to_stop_id].map((other) => (
            <Polyline
              key={`added-stop-${added.stop_id}-${other}`}
              positions={positions(stopMap, [other, added.stop_id])}
              interactive={false}
              pathOptions={{
                color: routes.get(added.route_id)?.color ?? REMOVED,
                weight: 5,
                opacity: journey ? 0.3 : 0.95,
                dashArray: '10 8',
              }}
            />
          )),
        )}
      </Pane>
      {addedStops.map((added) => (
        <CircleMarker
          key={`added-stop-${added.stop_id}`}
          center={[added.lat, added.lon]}
          radius={7}
          eventHandlers={{ click: () => mapSelect?.onStopClick(added.stop_id) }}
          pathOptions={{
            className: `stop-marker new-stop stop-${added.stop_id}`,
            color: routes.get(added.route_id)?.color ?? INK,
            weight: 4,
            fillColor: '#ffffff',
            fillOpacity: 1,
          }}
        >
          <Tooltip direction="top" offset={[0, -8]}>
            <strong>{added.name}</strong> <span style={{ color: '#8b95a5' }}>{added.stop_id}</span>
            <br />
            New stop on {routes.get(added.route_id)?.name ?? added.route_id} (this scenario)
            {clickHint}
          </Tooltip>
        </CircleMarker>
      ))}

      <CompactStopsWatcher stopCount={network.stops.length} onChange={setCompact} />
      {mapSelect && <MapClicks onClick={mapSelect.onMapClick} />}
      {network.source && <DataAttribution source={network.source} />}

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

/** Lines on a street are drawn on top of each other, so the tooltip lists them
 *  all (up to 10, then "+N more"), the line under the cursor first and in bold. */
const STREET_TOOLTIP_LINES = 10

function StreetTooltip({
  from,
  to,
  lines,
  underCursor,
  routes,
}: {
  from: string
  to: string
  lines: StreetLine[]
  underCursor: string
  routes: Map<string, Route>
}) {
  // The line under the cursor first (a click selects it), then the others in order.
  const ordered = [...lines.filter((l) => l.routeId === underCursor), ...lines.filter((l) => l.routeId !== underCursor)]
  const shown = ordered.slice(0, STREET_TOOLTIP_LINES)
  return (
    <>
      <strong>{from} – {to}</strong>
      {shown.map((line) => (
        <Fragment key={line.routeId}>
          <br />
          <span style={{ fontWeight: line.routeId === underCursor ? 700 : 400 }}>
            {routes.get(line.routeId)?.name ?? line.routeId} · {line.minutes} min
          </span>
        </Fragment>
      ))}
      {lines.length > shown.length && (
        <>
          <br />
          <span style={{ color: '#8b95a5' }}>+{lines.length - shown.length} more lines</span>
        </>
      )}
    </>
  )
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
  // "Before" is one dotted line through all its stops, walks included.
  const beforePath = positions(stops, journeyStopIds(journey.before))
  const walks = journey.after?.walks ?? []
  const origin = stops.get(journey.origin_id)
  const destination = stops.get(journey.destination_id)

  // Zoom smoothly to the journey when it (or the free map area) changes.
  // The parent passes a stable padding object, so this does not run on every render.
  useEffect(() => {
    const points = positions(stops, [...journeyStopIds(journey.before), ...journeyStopIds(journey.after)])
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
      {/* Walks: a dashed dark line (straight, like the estimate). */}
      {walks.map((walk) => (
        <Polyline
          key={`walk-${walk.before_leg}-${walk.from_stop_id}-${walk.to_stop_id}`}
          positions={positions(stops, [walk.from_stop_id, walk.to_stop_id])}
          pathOptions={{ color: INK, weight: 4, dashArray: '8 7', lineCap: 'butt' }}
        >
          <Tooltip sticky>
            Walk about {Math.round(walk.distance_m)} m · {walk.minutes.toFixed(1)} min
          </Tooltip>
        </Polyline>
      ))}
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

/** The timetable's publisher in the map's attribution line (always visible):
 *  the data's terms require naming the source. Details are in the legend. */
function DataAttribution({ source }: { source: NetworkSource }) {
  const map = useMap()
  useEffect(() => {
    const control = map.attributionControl
    const escape = (text: string) =>
      text.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c] ?? c)
    const name = escape(source.publisher)
    const text = source.attribution_url.startsWith('http')
      ? `Timetable: <a href="${escape(source.attribution_url)}" target="_blank" rel="noreferrer">${name}</a>`
      : `Timetable: ${name}`
    control.addAttribution(text)
    return () => {
      control.removeAttribution(text)
    }
  }, [map, source])
  return null
}

/** Reports clicks on the map itself (also clicks that hit a line). */
/**
 * Reports whether plain stops should be drawn small at the current zoom. It only
 * changes when a zoom crosses the threshold, so the thousands of lines of a big
 * network are not re-rendered on every zoom.
 */
function CompactStopsWatcher({ stopCount, onChange }: { stopCount: number; onChange: (compact: boolean) => void }) {
  const map = useMap()
  // Remember the last answer: even setting an unchanged state can make React render
  // the whole map once more (~150 ms for the full Gdańsk network).
  const last = useRef<boolean | null>(null)
  const report = useCallback(() => {
    const compact = compactStops(stopCount, map.getZoom())
    if (compact !== last.current) {
      last.current = compact
      onChange(compact)
    }
  }, [map, stopCount, onChange])
  useEffect(report, [report])
  useMapEvents({ zoomend: report })
  return null
}

function MapClicks({ onClick }: { onClick: (lat: number, lon: number) => void }) {
  useMapEvents({ click: (event) => onClick(event.latlng.lat, event.latlng.lng) })
  return null
}
