// Pure helpers over a journey plan from the backend. No React, no API calls.

import type { JourneyLeg, JourneyPlan, WalkLeg } from '../types/journey'
import type { SimulationSummary } from '../types/simulation'

export type JourneyStep =
  | { kind: 'walk'; walk: WalkLeg }
  | { kind: 'bus'; leg: JourneyLeg; index: number }

/** Walks and bus legs in journey order (a walk comes before the leg it names). */
export function journeySteps(plan: JourneyPlan): JourneyStep[] {
  const walksBefore = (index: number): JourneyStep[] =>
    plan.walks.filter((walk) => walk.before_leg === index).map((walk) => ({ kind: 'walk', walk }))
  return [
    ...plan.legs.flatMap((leg, index): JourneyStep[] => [...walksBefore(index), { kind: 'bus', leg, index }]),
    ...walksBefore(plan.legs.length),
  ]
}

/** Every stop the journey passes, in order (bus stops and both ends of each walk). */
export function journeyStopIds(plan: JourneyPlan | null | undefined): string[] {
  if (!plan) return []
  const ids = journeySteps(plan).flatMap((step) =>
    step.kind === 'walk' ? [step.walk.from_stop_id, step.walk.to_stop_id] : step.leg.stop_ids,
  )
  return ids.filter((id, i) => i === 0 || id !== ids[i - 1])
}

function metres(value: number): string {
  return `${value.toLocaleString('en-GB')} m`
}

/** One sentence on how passengers walk in the simulation (the backend's settings). */
export function describeWalking(walking: SimulationSummary['walking']): string {
  if (!walking) return 'Nobody walks: journeys to or from a closed stop are left out.'
  const how = `at ${walking.speed_kmh} km/h, distance = straight line × 1.3`
  return walking.between_open_stops
    ? `Passengers may walk up to ${metres(walking.max_walk_m)} at the start or end and up to ` +
        `${metres(walking.max_transfer_walk_m)} between two buses (${how}).`
    : `Passengers walk only from or to a closed stop, up to ${metres(walking.max_walk_m)} (${how}).`
}
