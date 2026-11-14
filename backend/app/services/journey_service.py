"""Journey explorer: explain ONE journey before and after a scenario.

Uses the same graphs as the simulation (route_graph.py with walking.py's
walking layer), so its times and statuses always match the simulation results.
The legs come directly from the fastest path: consecutive platforms of the
same route are one leg; every change of bus starts a new one; walk edges are
the walks.
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
from app.services.route_graph import added_stop_ids, build_route_graph
from app.services.simulation_service import apply_scenario, stop_places
from app.services.walking import WalkingModel, WalkNode, add_walking_layer, fastest_journey

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

    With ``walking``, passengers walk exactly as in the simulation (e.g. from
    a closed stop to a nearby open one) instead of the journey being impossible.

    A stop ADDED by the changes may be the origin or destination: such a
    journey has no "before" (status "new" when it is possible after).

    Raises JourneyError for unknown stops and ScenarioError for invalid changes.
    """
    before_graph = build_route_graph(baseline, transfer_penalty_min, include_waiting)
    add_walking_layer(before_graph, baseline, walking, closed=())
    if request.changes:
        after_graph, closed = apply_scenario(
            baseline, Scenario(changes=request.changes), transfer_penalty_min, include_waiting
        )
        add_walking_layer(after_graph, stop_places(baseline, after_graph), walking, closed)
    else:
        after_graph, closed = before_graph, set()

    known = set(baseline.nodes) | set(added_stop_ids(after_graph))
    for stop_id in (request.origin_id, request.destination_id):
        if stop_id not in known:
            raise JourneyError(f"Unknown stop '{stop_id}'")

    origin, destination = request.origin_id, request.destination_id
    in_baseline = origin in baseline and destination in baseline
    before = _plan(before_graph, origin, destination, set()) if in_baseline else None

    after: tuple[JourneyPlan, float] | None = None
    reason: str | None = None
    touches_closed = origin in closed or destination in closed
    if touches_closed and walking is None:
        which = "origin" if origin in closed else "destination"
        reason = f"The {which} stop is closed in this scenario."
    else:
        after = _plan(after_graph, origin, destination, closed)
        if after is None and touches_closed and walking is not None:
            reason = (
                f"The {'origin' if origin in closed else 'destination'} stop is closed and no "
                f"open stop is within {walking.max_walk_m:g} m walking, or none of them is connected."
            )
        elif after is None:
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

    if not in_baseline:
        if after is None:
            return comparison("impossible", None, reason or "The new stop is not connected to this stop.")
        return comparison("new", None, "A journey to or from a new stop: there is no \"before\".")
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
    walking: WalkingModel | None = None,
) -> JourneyPlan | None:
    """Fastest journey in the (unchanged) network split into legs, or None."""
    graph = build_route_graph(network, transfer_penalty_min, include_waiting)
    add_walking_layer(graph, network, walking, closed=())
    planned = _plan(graph, origin, destination, set())
    return planned[0] if planned else None


def _plan(
    graph: nx.DiGraph, origin: str, destination: str, closed: set[str]
) -> tuple[JourneyPlan, float] | None:
    """(plan, unrounded travel time) or None if unreachable."""
    path = fastest_journey(graph, origin, destination)
    if path is None:
        return None

    legs: list[JourneyLeg] = []
    walks: list[tuple[WalkLeg, bool]] = []  # (walk, before any bus)
    in_vehicle = wait = walk_minutes = 0.0
    previous = None
    for index, node in enumerate(path.nodes):
        edge = graph.edges[path.nodes[index - 1], node] if index else None
        if edge is not None and edge["kind"] == "walk":
            walk_minutes += edge["minutes"]
            walks.append((_walk_leg(path.nodes[index - 1], node, edge), not legs))
        if isinstance(node, WalkNode) and node.kind == "off":  # rode here, then walks
            assert previous is not None and edge is not None
            legs[-1].stop_ids.append(node.stop_id)
            legs[-1].travel_time_min += edge["weight"]
            in_vehicle += edge["weight"]
        if not isinstance(node, tuple):  # a stop or walking node: boarding, alighting, walking
            previous = None
            continue
        stop_id, route_id = node
        following = path.nodes[index + 1] if index + 1 < len(path.nodes) else None
        rides_on = isinstance(following, tuple) or (isinstance(following, WalkNode) and following.kind == "off")
        if previous is None and not rides_on:
            # Boarded and got off at once: costs the wait (the first boarding's
            # penalty is not counted), so it only ties with not boarding when
            # there is no waiting. Not a leg.
            continue
        if previous is None:  # boarded: a new leg starts here
            assert edge is not None
            leg_wait: float = edge["wait_min"]
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
        walk_min=_round(walk_minutes),
        walk_start=next((w for w, at_start in walks if at_start), None),
        walk_end=next((w for w, at_start in walks if not at_start), None),
        transfers=max(len(legs) - 1, 0),
        transfer_penalty_min=penalty,
        legs=legs,
    )
    return plan, path.travel_time_min


def _stop_of(node: object) -> str:
    return node.stop_id if isinstance(node, WalkNode) else str(node)


def _walk_leg(from_node: object, to_node: object, edge: dict[str, float]) -> WalkLeg:
    return WalkLeg(
        from_stop_id=_stop_of(from_node),
        to_stop_id=_stop_of(to_node),
        distance_m=round(edge["distance_m"], -1),  # to 10 m: it is an estimate
        minutes=_round(edge["minutes"]),
    )


def _round(value: float) -> float:
    return round(value, 1) + 0.0  # "+ 0.0" turns -0.0 into 0.0
