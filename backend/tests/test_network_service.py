"""Graph building and shortest-journey calculation."""

from itertools import permutations

import networkx as nx
import pytest
from sqlalchemy.orm import Session

from app.models import Connection, Stop
from app.seed.sample_network import ROUTES, STOPS
from app.services.network_service import (
    Journey,
    UnknownStopError,
    build_graph,
    build_graph_from_db,
    shortest_journey,
)


def _stop(stop_id: str) -> Stop:
    return Stop(id=stop_id, name=stop_id, lat=0.0, lon=0.0)


def _conn(route: str, a: str, b: str, minutes: float) -> Connection:
    return Connection(route_id=route, from_stop_id=a, to_stop_id=b, travel_time_min=minutes)


@pytest.fixture
def small_graph() -> nx.DiGraph:
    """A -> B -> C (5 + 5 min) and a slow direct A -> C (15 min). One-way only."""
    return build_graph(
        [_stop("A"), _stop("B"), _stop("C"), _stop("D")],
        [_conn("R1", "A", "B", 5), _conn("R1", "B", "C", 5), _conn("R2", "A", "C", 15)],
    )


# --- build_graph ------------------------------------------------------------

def test_stops_become_nodes_and_connections_become_weighted_edges(
    small_graph: nx.DiGraph,
) -> None:
    assert set(small_graph.nodes) == {"A", "B", "C", "D"}
    assert small_graph.number_of_edges() == 3
    assert small_graph.edges["A", "B"]["weight"] == 5
    assert small_graph.edges["A", "B"]["routes"] == ["R1"]


def test_graph_is_directed(small_graph: nx.DiGraph) -> None:
    assert small_graph.has_edge("A", "B")
    assert not small_graph.has_edge("B", "A")


def test_parallel_connections_merge_into_fastest_edge() -> None:
    graph = build_graph(
        [_stop("A"), _stop("B")],
        [_conn("R2", "A", "B", 4), _conn("R1", "A", "B", 2), _conn("R3", "A", "B", 6)],
    )

    assert graph.number_of_edges() == 1
    assert graph.edges["A", "B"]["weight"] == 2
    assert graph.edges["A", "B"]["routes"] == ["R1", "R2", "R3"]
    assert graph.edges["A", "B"]["route_times"] == {"R1": 2, "R2": 4, "R3": 6}


def test_connection_to_unknown_stop_is_rejected() -> None:
    with pytest.raises(UnknownStopError, match="'X'"):
        build_graph([_stop("A")], [_conn("R1", "A", "X", 3)])


# --- shortest_journey -------------------------------------------------------

def test_shortest_journey_picks_fastest_path_not_fewest_stops(
    small_graph: nx.DiGraph,
) -> None:
    assert shortest_journey(small_graph, "A", "C") == Journey(["A", "B", "C"], 10.0)


def test_journey_to_same_stop_takes_no_time(small_graph: nx.DiGraph) -> None:
    assert shortest_journey(small_graph, "B", "B") == Journey(["B"], 0.0)


def test_unreachable_destination_returns_none(small_graph: nx.DiGraph) -> None:
    assert shortest_journey(small_graph, "C", "A") is None  # wrong direction
    assert shortest_journey(small_graph, "A", "D") is None  # isolated stop


def test_unknown_stop_raises(small_graph: nx.DiGraph) -> None:
    with pytest.raises(UnknownStopError):
        shortest_journey(small_graph, "A", "NOPE")
    with pytest.raises(UnknownStopError):
        shortest_journey(small_graph, "NOPE", "A")


# --- sample network loaded from the database ---------------------------------

def test_graph_from_db_contains_whole_sample_network(db: Session) -> None:
    graph = build_graph_from_db(db)

    assert graph.number_of_nodes() == len(STOPS)
    # MKT<->CEN is served by R1 and R4, so 2 directed connections merge.
    total_connections = sum(len(r.travel_times_min) * 2 for r in ROUTES)
    assert graph.number_of_edges() == total_connections - 2
    assert graph.edges["MKT", "CEN"] == {
        "weight": 2.0,
        "routes": ["R1", "R4"],
        "route_times": {"R1": 3.0, "R4": 2.0},
    }


def test_every_stop_can_reach_every_other_stop(db: Session) -> None:
    graph = build_graph_from_db(db)

    for origin, destination in permutations(graph.nodes, 2):
        assert shortest_journey(graph, origin, destination) is not None


def test_known_journey_in_sample_network(db: Session) -> None:
    graph = build_graph_from_db(db)

    # North Park -> Airport: R1 to MKT (7), R4 MKT->CEN->STD->TEC->AIR (2+4+4+6).
    journey = shortest_journey(graph, "NTH", "AIR")

    assert journey == Journey(["NTH", "UNI", "MKT", "CEN", "STD", "TEC", "AIR"], 23.0)
