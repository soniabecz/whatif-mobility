// The change being built in the scenario form. Kept outside the form so the
// map can edit it too (click a stop or a line). Pure functions: no React.

import type { Network } from '../types/network'
import {
  MAX_CHANGES,
  MAX_TRAVEL_TIME_MIN,
  type ChangeType,
  type ScenarioChange,
} from '../types/scenario'
import { currentTravelTime, linkKey, neighbours, sortedStops } from './network'

export interface ChangeDraft {
  type: ChangeType
  /** Stop for "close stop". */
  stopId: string
  /** Link for "remove link" / "travel time". */
  fromId: string
  toId: string
  /** Text of the travel time input (validated in buildChange). */
  travelTime: string
  bothDirections: boolean
  /** True after a map click set From: the next click on a neighbour sets To. */
  awaitingTo: boolean
}

function timeText(network: Network, fromId: string, toId: string): string {
  return String(currentTravelTime(network, fromId, toId) ?? '')
}

export function initialDraft(network: Network): ChangeDraft {
  const first = sortedStops(network)[0]?.id ?? ''
  const to = neighbours(network, first)[0]?.id ?? ''
  return {
    type: 'close_stop',
    stopId: first,
    fromId: first,
    toId: to,
    travelTime: timeText(network, first, to),
    bothDirections: true,
    awaitingTo: false,
  }
}

export function withType(draft: ChangeDraft, type: ChangeType): ChangeDraft {
  return { ...draft, type, awaitingTo: false }
}

/** A link was chosen: fill in its current travel time. */
export function withLink(
  network: Network,
  draft: ChangeDraft,
  fromId: string,
  toId: string,
): ChangeDraft {
  return { ...draft, fromId, toId, travelTime: timeText(network, fromId, toId), awaitingTo: false }
}

/** From changed (dropdown): To becomes its first neighbour. */
export function withFrom(network: Network, draft: ChangeDraft, fromId: string): ChangeDraft {
  return withLink(network, draft, fromId, neighbours(network, fromId)[0]?.id ?? '')
}

/**
 * A stop was clicked on the map.
 * - "Close stop": it becomes the stop.
 * - Link types: it becomes From, unless From was just picked and this is one
 *   of its neighbours; then it becomes To.
 */
export function clickStop(network: Network, draft: ChangeDraft, stopId: string): ChangeDraft {
  if (draft.type === 'close_stop') return { ...draft, stopId, awaitingTo: false }
  const isNeighbour = neighbours(network, draft.fromId).some((stop) => stop.id === stopId)
  if (draft.awaitingTo && isNeighbour) return withLink(network, draft, draft.fromId, stopId)
  return { ...withFrom(network, draft, stopId), awaitingTo: true }
}

/** A line was clicked on the map: select that link ("close stop" switches to "remove link"). */
export function clickLink(
  network: Network,
  draft: ChangeDraft,
  fromId: string,
  toId: string,
): ChangeDraft {
  const type = draft.type === 'close_stop' ? 'remove_connection' : draft.type
  return withLink(network, { ...draft, type }, fromId, toId)
}

/** What the map highlights as "currently selected in the form". */
export interface DraftSelection {
  stopIds: string[]
  /** linkKey of the selected street, if a link type is chosen. */
  link: string | null
}

export function draftSelection(draft: ChangeDraft): DraftSelection {
  if (draft.type === 'close_stop') {
    return { stopIds: draft.stopId ? [draft.stopId] : [], link: null }
  }
  const stopIds = [draft.fromId, draft.toId].filter((id) => id !== '')
  return { stopIds, link: draft.fromId && draft.toId ? linkKey(draft.fromId, draft.toId) : null }
}

/** Validate the draft; returns the change or an error message for the user. */
export function buildChange(draft: ChangeDraft, changeCount: number): ScenarioChange | string {
  if (changeCount >= MAX_CHANGES) return `A scenario can have at most ${MAX_CHANGES} changes.`
  if (draft.type === 'close_stop') {
    if (!draft.stopId) return 'Choose a stop.'
    return { type: 'close_stop', stop_id: draft.stopId }
  }
  if (!draft.fromId || !draft.toId) return 'Choose both stops of the connection.'
  if (draft.type === 'remove_connection') {
    return {
      type: 'remove_connection',
      from_stop_id: draft.fromId,
      to_stop_id: draft.toId,
      both_directions: draft.bothDirections,
    }
  }
  const minutes = Number(draft.travelTime)
  if (draft.travelTime.trim() === '' || !Number.isFinite(minutes) || minutes <= 0) {
    return 'Travel time must be a number greater than 0.'
  }
  if (minutes > MAX_TRAVEL_TIME_MIN) {
    return `Travel time can be at most ${MAX_TRAVEL_TIME_MIN} minutes.`
  }
  return {
    type: 'change_travel_time',
    from_stop_id: draft.fromId,
    to_stop_id: draft.toId,
    travel_time_min: minutes,
    both_directions: draft.bothDirections,
  }
}
