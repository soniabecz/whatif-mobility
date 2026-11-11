"""Journey explorer: explain ONE journey before and after a scenario.

Uses the same graphs and shortest paths as the simulation, so its times and
statuses always match the simulation results; it only adds the stop-by-stop
route split into legs.

Legs: there is no transfer penalty yet, so the path does not say which bus a
passenger takes. Each stretch gets the route that is fastest on it; when
several are equally fast the passenger stays on the current bus, otherwise the
route that continues furthest is chosen (ties: alphabetical). Deterministic,
and leg times always add up to the journey time.
"""

import networkx as nx

from app.schemas.journey import (
    JourneyComparison,
    JourneyComparisonStatus,
    JourneyLeg,
    JourneyPlan,
    JourneyRequest,
)
from app.schemas.scenario import Scenario
from app.services.network_service import shortest_journey
from app.services.simulation_service import apply_scenario

# Same tolerance as the simulation: guards against float noise.
_EPSILON = 1e-9


class JourneyError(ValueError):
    """The request refers to something not in the network (e.g. unknown stop)."""


def compare_journey(baseline: nx.DiGraph, request: JourneyRequest) -> JourneyComparison:
    """Fastest journey before and after the request's changes.

    Raises JourneyError for unknown stops and ScenarioError for invalid changes.
    """
    for stop_id in (request.origin_id, request.destination_id):
        if stop_id not in baseline:
            raise JourneyError(f"Unknown stop '{stop_id}'")

    if request.changes:
        modified, closed = apply_scenario(baseline, Scenario(changes=request.changes))
    else:
        modified, closed = baseline, set()

    origin, destination = request.origin_id, request.destination_id
    before = _plan(baseline, origin, destination)

    after: tuple[JourneyPlan, float] | None = None
    reason: str | None = None
    if origin in closed:
        reason = "The origin stop is closed in this scenario."
    elif destination in closed:
        reason = "The destination stop is closed in this scenario."
    else:
        after = _plan(modified, origin, destination)
        if after is None:
            reason = "No connection remains between these stops after the changes."

    def comparison(status: JourneyComparisonStatus, change: float | None,
                   why: str | None) -> JourneyComparison:
        return JourneyComparison(
            origin_id=origin,
            destination_id=destination,
            before=before[0] if before else None,
            after=after[0] if after else None,
            status=status,
            change_min=change,
            reason=why,
        )

    if before is None:
        return comparison("unreachable", None, "These stops are not connected in the current network.")
    if after is None:
        return comparison("impossible", None, reason)

    # Compare unrounded totals (exactly as the simulation does); report rounded.
    difference = after[1] - before[1]
    if abs(difference) < _EPSILON:
        return comparison("unchanged", 0.0, None)
    return comparison("slower" if difference > 0 else "faster", _round(difference), None)


def plan_journey(graph: nx.DiGraph, origin: str, destination: str) -> JourneyPlan | None:
    """Fastest journey split into legs, or None if unreachable."""
    planned = _plan(graph, origin, destination)
    return planned[0] if planned else None


def _plan(graph: nx.DiGraph, origin: str, destination: str) -> tuple[JourneyPlan, float] | None:
    """(plan, unrounded travel time) or None if unreachable."""
    journey = shortest_journey(graph, origin, destination)
    if journey is None:
        return None
    hops = list(zip(journey.stop_ids, journey.stop_ids[1:]))
    plan = JourneyPlan(
        travel_time_min=_round(journey.travel_time_min),
        legs=_split_into_legs(graph, hops),
    )
    return plan, journey.travel_time_min


def _fastest_routes(graph: nx.DiGraph, u: str, v: str) -> list[str]:
    edge = graph.edges[u, v]
    return sorted(
        route_id for route_id, minutes in edge["route_times"].items()
        if abs(minutes - edge["weight"]) < _EPSILON
    )


def _split_into_legs(graph: nx.DiGraph, hops: list[tuple[str, str]]) -> list[JourneyLeg]:
    candidates = [_fastest_routes(graph, u, v) for u, v in hops]

    def run_length(route_id: str, start: int) -> int:
        """How many consecutive hops from `start` this route is fastest on."""
        length = 0
        while start + length < len(hops) and route_id in candidates[start + length]:
            length += 1
        return length

    # Assign a route to every hop: stay on the current bus while it is among
    # the fastest; otherwise take the route that continues furthest.
    assigned: list[str] = []
    for index in range(len(hops)):
        if assigned and assigned[-1] in candidates[index]:
            assigned.append(assigned[-1])
        else:
            assigned.append(min(candidates[index], key=lambda r: (-run_length(r, index), r)))

    legs: list[JourneyLeg] = []
    for index, ((u, v), route_id) in enumerate(zip(hops, assigned)):
        edge = graph.edges[u, v]
        via: list[str] = edge.get("route_via", {}).get(route_id, [])
        minutes = edge["route_times"][route_id]
        if index > 0 and assigned[index - 1] == route_id:
            leg = legs[-1]
            leg.stop_ids.extend([*via, v])
            leg.passes_closed_stop_ids.extend(via)
            leg.travel_time_min += minutes
        else:
            legs.append(JourneyLeg(
                route_id=route_id,
                stop_ids=[u, *via, v],
                travel_time_min=minutes,
                passes_closed_stop_ids=list(via),
            ))
    for leg in legs:
        leg.travel_time_min = _round(leg.travel_time_min)
    return legs


def _round(value: float) -> float:
    return round(value, 1) + 0.0  # "+ 0.0" turns -0.0 into 0.0
