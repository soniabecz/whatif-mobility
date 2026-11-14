"""The fast engine (Day 14, step B): compiled all-pairs times, the baseline
cache and order-preserving sums give exactly the results of the per-origin
NetworkX search they replace."""

import math
from functools import reduce
from operator import add

import networkx as nx
import numpy as np
import pytest
from sqlalchemy.orm import Session

from app.schemas.scenario import Scenario
from app.services import simulation_service
from app.services.network_service import build_graph_from_db
from app.services.route_graph import build_route_graph, travel_time_matrix, travel_times_from
from app.services.simulation_service import _ordered_sum, baseline_times, journey_matrix, scenario_state
from app.services.walking import WalkingModel


@pytest.fixture
def sample(db: Session) -> nx.DiGraph:
    return build_graph_from_db(db)


@pytest.mark.parametrize(("penalty", "waiting"), [(0.0, False), (2.0, True), (5.0, False)])
def test_matrix_equals_the_per_origin_search(sample: nx.DiGraph, penalty: float, waiting: bool) -> None:
    graph = build_route_graph(sample, penalty, waiting)
    stops = sorted(sample.nodes)
    matrix = travel_time_matrix(graph, stops)
    for origin in stops:
        expected = travel_times_from(graph, origin)
        for destination in stops:
            assert matrix.get(origin, destination) == expected.get(destination)  # exact, not approximate


def test_zero_weight_edges_and_unreachable_stops() -> None:
    graph = nx.DiGraph(transfer_penalty_min=0.0)
    graph.add_edge("A", "B", weight=0.0)  # like alighting: free
    graph.add_edge("B", "C", weight=2.5)
    graph.add_node("D")
    matrix = travel_time_matrix(graph, ["A", "B", "C", "D"])
    assert (matrix.get("A", "B"), matrix.get("A", "C"), matrix.get("A", "D"), matrix.get("C", "A")) == (
        0.0, 2.5, None, None)
    assert matrix.get("A", "A") is None and matrix.get("A", "X") is None
    with pytest.raises(ValueError):
        matrix.values[0, 1] = 9.0  # read-only: shared through the cache


def test_baseline_cache_follows_the_network(sample: nx.DiGraph) -> None:
    simulation_service._BASELINE_CACHE.clear()
    first = baseline_times(sample, 2.0, True)
    assert baseline_times(build_graph_from_db_copy(sample), 2.0, True) is first  # same network: reused
    assert baseline_times(sample, 0.0, True) is not first  # other settings
    changed = sample.copy()
    changed.edges["CEN", "MKT"]["route_times"] = {"R1": 30.0, "R4": 30.0}
    assert baseline_times(changed, 2.0, True).get("CEN", "MKT") != first.get("CEN", "MKT")


def build_graph_from_db_copy(graph: nx.DiGraph) -> nx.DiGraph:
    """An equal network in a new graph object (as each request builds one)."""
    copy = nx.DiGraph()
    copy.graph.update(graph.graph)
    copy.add_nodes_from(graph.nodes(data=True))
    copy.add_edges_from(graph.edges(data=True))
    return copy


def test_ordered_sum_matches_a_plus_equals_loop() -> None:
    values = np.array([0.1] * 10 + [1e16, 1.0, -1e16, 0.3])
    assert _ordered_sum(values) == reduce(add, values.tolist(), 0.0)
    assert _ordered_sum(values) != math.fsum(values.tolist())  # i.e. not a compensated sum
    assert _ordered_sum(np.array([])) == 0.0


def test_journey_matrix_marks_closed_stops(sample: nx.DiGraph) -> None:
    scenario = Scenario.model_validate({"changes": [{"type": "close_stop", "stop_id": "CEN"}]})
    stops = sorted(sample.nodes)
    cen = stops.index("CEN")
    _, excluded = journey_matrix(scenario_state(sample, scenario), stops)
    assert excluded[cen].sum() == len(stops) and excluded[:, cen].sum() == len(stops)
    walking = scenario_state(sample, scenario, walking=WalkingModel(5, 1000))
    times, excluded = journey_matrix(walking, stops)
    assert not excluded.any()
    assert times[cen, stops.index("AIR")] == walking.times.get("CEN", "AIR")
    assert np.isfinite(times[cen, stops.index("AIR")])  # reached on foot
