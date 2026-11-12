"""Journey explorer: explain ONE journey before and after a scenario.

Uses the same route-aware graphs as the simulation (route_graph.py), so its
times and statuses always match the simulation results. The legs come
directly from the fastest path: consecutive platforms of the same route are
one leg; every change of bus starts a new one.
"""

import networkx as nx

from app.schemas.journey import (
    JourneyComparison,
    JourneyComparisonStatus,
    JourneyLeg,
    JourneyPlan,
    JourneyRequest,
    WalkLeg,
)
from app.schemas.scenario import Scenario
from app.services.route_graph import build_route_graph, fastest_path, travel_times_from
from app.services.simulation_service import apply_scenario
from app.services.walking import Walk, WalkingModel, best_walk_option

# Same tolerance as the simulation: guards against float noise.
_EPSILON = 1e-9


class JourneyError(ValueError):
    """The request refers to something not in the network (e.g. unknown stop)."""


def compare_journey(
    baseline: nx.DiGraph,
    request: JourneyRequest,
    transfer_penalty_min: float = 0.0,
    include_waiting: bool = False,
    walking: WalkingModel | None = None,
) -> JourneyComparison:
    """Fastest journey before and after the request's changes.

    With ``walking``, a journey to or from a closed stop walks to a nearby
    open stop (exactly as the simulation does) instead of being impossible.

    Raises JourneyError for unknown stops and ScenarioError for invalid changes.
    """
    for stop_id in (request.origin_id, request.destination_id):
        if stop_id not in baseline:
            raise JourneyError(f"Unknown stop '{stop_id}'")

    before_graph = build_route_graph(baseline, transfer_penalty_min, include_waiting)
    if request.changes:
        after_graph, closed = apply_scenario(
            baseline, Scenario(changes=request.changes), transfer_penalty_min, include_waiting
        )
    else:
        after_graph, closed = before_graph, set()

    origin, destination = request.origin_id, request.destination_id
    before = _plan(before_graph, origin, destination, set())

    after: tuple[JourneyPlan, float] | None = None
    reason: str | None = None
    if (origin in closed or destination in closed) and walking is not None:
        after = _walk_plan(baseline, after_graph, walking, origin, destination, closed)
        if after is None:
            reason = (
                f"The {'origin' if origin in closed else 'destination'} stop is closed and no "
                f"open stop is within {walking.max_walk_m:g} m walking, or none of them is connected."
            )
    elif origin in closed:
        reason = "The origin stop is closed in this scenario."
    elif destination in closed:
        reason = "The destination stop is closed in this scenario."
    else:
        after = _plan(after_graph, origin, destination, closed)
        if after is None:
            reason = "No connection remains between these stops after the changes."

    def comparison(
        status: JourneyComparisonStatus, change: float | None, why: str | None
    ) -> JourneyComparison:
        return JourneyComparison(
            origin_id=origin,
            destination_id=destination,
            before=before[0] if before else None,
            after=after[0] if after else None,
            status=status,
            change_min=change,
            reason=why,
        )

    if before is None and after is not None:
        return comparison("new", None, "Not possible in the current network; the changes connect these stops.")
    if before is None:
        return comparison("unreachable", None, "These stops are not connected in the current network.")
    if after is None:
        return comparison("impossible", None, reason)

    # Compare unrounded totals (exactly as the simulation does); report rounded.
    difference = after[1] - before[1]
    if abs(difference) < _EPSILON:
        return comparison("unchanged", 0.0, None)
    return comparison("slower" if difference > 0 else "faster", _round(difference), None)


def plan_journey(
    network: nx.DiGraph,
    origin: str,
    destination: str,
    transfer_penalty_min: float = 0.0,
    include_waiting: bool = False,
) -> JourneyPlan | None:
    """Fastest journey in the (unchanged) network split into legs, or None."""
    graph = build_route_graph(network, transfer_penalty_min, include_waiting)
    planned = _plan(graph, origin, destination, set())
    return planned[0] if planned else None


def _plan(
    graph: nx.DiGraph, origin: str, destination: str, closed: set[str]
) -> tuple[JourneyPlan, float] | None:
    """(plan, unrounded travel time) or None if unreachable."""
    path = fastest_path(graph, origin, destination)
    if path is None:
        return None

    legs: list[JourneyLeg] = []
    in_vehicle = wait = 0.0
    previous = None
    for index, node in enumerate(path.nodes):
        if not isinstance(node, tuple):  # a stop node: boarding or alighting
            previous = None
            continue
        stop_id, route_id = node
        if previous is None:  # boarded: a new leg starts here
            leg_wait: float = graph.edges[path.nodes[index - 1], node]["wait_min"]
            wait += leg_wait
            legs.append(JourneyLeg(
                route_id=route_id, stop_ids=[stop_id], travel_time_min=0.0,
                wait_min=leg_wait, passes_closed_stop_ids=[],
            ))
        else:
            minutes: float = graph.edges[previous, node]["weight"]
            legs[-1].stop_ids.append(stop_id)
            legs[-1].travel_time_min += minutes
            in_vehicle += minutes
        previous = node

    for leg in legs:
        # Stops passed (not the leg's first or last) that are closed.
        leg.passes_closed_stop_ids = [s for s in leg.stop_ids[1:-1] if s in closed]
        leg.travel_time_min = _round(leg.travel_time_min)

    penalty: float = graph.graph["transfer_penalty_min"]
    plan = JourneyPlan(
        travel_time_min=_round(path.travel_time_min),
        in_vehicle_min=_round(in_vehicle),
        wait_min=_round(wait),
        walk_min=0.0,
        walk_start=None,
        walk_end=None,
        transfers=len(legs) - 1,
        transfer_penalty_min=penalty,
        legs=legs,
    )
    return plan, path.travel_time_min


def _walk_plan(
    baseline: nx.DiGraph,
    after_graph: nx.DiGraph,
    walking: WalkingModel,
    origin: str,
    destination: str,
    closed: set[str],
) -> tuple[JourneyPlan, float] | None:
    """Walk + bus (+ walk) plan for a journey touching a closed stop, or None.

    Uses the same option and the same bus times as the simulation.
    """
    times: dict[str, dict[str, float]] = {}

    def bus_time(a: str, b: str) -> float | None:
        if a not in times:
            times[a] = travel_times_from(after_graph, a)
        return times[a].get(b)

    option = best_walk_option(baseline, walking, origin, destination, closed, bus_time)
    if option is None:
        return None

    if option.bus_from is None or option.bus_to is None:  # walking the whole way
        bus = JourneyPlan(
            travel_time_min=0.0, in_vehicle_min=0.0, wait_min=0.0, walk_min=0.0,
            walk_start=None, walk_end=None, transfers=0,
            transfer_penalty_min=after_graph.graph["transfer_penalty_min"], legs=[],
        )
    else:
        planned = _plan(after_graph, option.bus_from, option.bus_to, closed)
        if planned is None:  # pragma: no cover - bus_time found a path
            return None
        bus = planned[0]

    walks = [w for w in (option.walk_start, option.walk_end) if w is not None]
    plan = bus.model_copy(update={
        "travel_time_min": _round(option.total_min),
        "walk_min": _round(sum(w.minutes for w in walks)),
        "walk_start": _walk_leg(option.walk_start),
        "walk_end": _walk_leg(option.walk_end),
    })
    return plan, option.total_min


def _walk_leg(walk: Walk | None) -> WalkLeg | None:
    if walk is None:
        return None
    return WalkLeg(
        from_stop_id=walk.from_stop_id,
        to_stop_id=walk.to_stop_id,
        distance_m=round(walk.distance_m, -1),  # to 10 m: it is an estimate
        minutes=_round(walk.minutes),
    )


def _round(value: float) -> float:
    return round(value, 1) + 0.0  # "+ 0.0" turns -0.0 into 0.0
