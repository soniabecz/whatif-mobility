"""Network text for the AI prompt, and excerpts of it for big networks (Day 14).

A line is written as stop chains with the minutes between stops:
"A -3- B" (both ways, 3 min), "A -2/3- B" (2 min there, 3 back), "A >3> B" (one
way). A whole city does not fit the AI provider's free tier (8,000 tokens per
minute), so for big networks the prompt gets an EXCERPT: the stations named in
the request (or used by the current changes), the lines through them around
those stations, lines named by number, and a one-line list of every line.

Station names are matched without diacritics and by word stems, so Polish
case endings still match: "Bramy Wyżynnej" finds "Brama Wyżynna".
"""

import re
import unicodedata
from collections.abc import Iterable, Sequence

import networkx as nx

from app.schemas.scenario import (
    AddConnection,
    AddRoute,
    AddStop,
    ChangeFrequency,
    ChangeTravelTime,
    CloseStop,
    RemoveConnection,
    ScenarioChange,
)

LINES_LEGEND = (
    "LINES: each route as stop sequences. \"A -3- B\": the route runs directly between "
    "A and B in 3 min both ways; \"A -2/3- B\": 2 min from A to B, 3 min back; "
    "\"A >3> B\": one way only. Stops written next to each other are directly linked."
)
WINDOW = 3  # stops shown on each side of a named station
_MIN_WORD = 4  # shorter name words (SKM, PKP, II, ul) are not needed to match
_MAX_STATIONS = 12  # more matches than this: the request is too vague to excerpt


# --- Line chains ---------------------------------------------------------------------------

def _chains(edges: dict[tuple[str, str], float], two_way: bool) -> list[list[str]]:
    """Split one route's links into chains of stops (each link used once).

    ``two_way``: ``edges`` holds each street once (a < b) and is walked both ways.
    """
    neighbours: dict[str, list[str]] = {}
    for a, b in edges:
        neighbours.setdefault(a, []).append(b)
        if two_way:
            neighbours.setdefault(b, []).append(a)
    unused = set(edges)

    def key(a: str, b: str) -> tuple[str, str]:
        return (min(a, b), max(a, b)) if two_way else (a, b)

    def degree(node: str) -> int:
        return sum(key(node, n) in unused for n in neighbours.get(node, []))

    incoming: dict[str, int] = {}
    if not two_way:
        for _, b in edges:
            incoming[b] = incoming.get(b, 0) + 1
    chains: list[list[str]] = []
    while unused:
        nodes = sorted({n for pair in unused for n in pair})
        # Start at an end of the line when there is one.
        ends = [n for n in nodes if (degree(n) % 2 == 1 if two_way else degree(n) > incoming.get(n, 0))]
        current = (ends or [n for n in nodes if degree(n) > 0])[0]
        chain = [current]
        while True:
            options = sorted(n for n in neighbours.get(current, []) if key(current, n) in unused)
            if not options:
                break
            nxt = options[0]
            unused.discard(key(current, nxt))
            if not two_way:
                incoming[nxt] -= 1
            chain.append(nxt)
            current = nxt
        chains.append(chain)
    return chains


def route_chains(graph: nx.DiGraph) -> dict[str, list[list[str]]]:
    """Per route, its chains as tokens: [stop, link, stop, link, ..., stop]."""
    per_route: dict[str, dict[tuple[str, str], float]] = {}
    for u, v, edge in graph.edges(data=True):
        for route_id, minutes in edge["route_times"].items():
            per_route.setdefault(route_id, {})[(u, v)] = minutes

    result: dict[str, list[list[str]]] = {}
    for route_id in sorted(per_route):
        times = per_route[route_id]
        # Streets the route runs both ways (times may differ), and one-way links.
        both = {(min(a, b), max(a, b)): 0.0 for (a, b) in times if (b, a) in times}
        one_way = {(a, b): t for (a, b), t in times.items() if (min(a, b), max(a, b)) not in both}

        def two_way_link(a: str, b: str) -> str:
            there, back = times[(a, b)], times[(b, a)]
            return f"-{there:g}-" if there == back else f"-{there:g}/{back:g}-"

        chains = []
        for chain in _chains(both, two_way=True):
            chains.append([t for a, b in zip(chain, chain[1:]) for t in (a, two_way_link(a, b))] + [chain[-1]])
        for chain in _chains(one_way, two_way=False):
            chains.append([t for a, b in zip(chain, chain[1:]) for t in (a, f">{one_way[(a, b)]:g}>")] + [chain[-1]])
        result[route_id] = chains
    return result


def _route_label(graph: nx.DiGraph, route_id: str) -> str:
    name = graph.graph.get("route_names", {}).get(route_id, route_id)
    headways: dict[str, float] = graph.graph.get("headways", {})
    headway = f", every {headways[route_id]:g} min" if route_id in headways else ""
    return f"{route_id} ({name}{headway})"


def describe_lines(graph: nx.DiGraph) -> str:
    """Compact description: each route once, as stop sequences with the minutes
    between consecutive stops. Covers every link of every route."""
    lines = ["STOPS (id: name):", *(f"- {s}: {graph.nodes[s]['name']}" for s in sorted(graph.nodes))]
    lines += ["", LINES_LEGEND]
    for route_id, chains in route_chains(graph).items():
        lines.append(f"- {_route_label(graph, route_id)}: " + "; ".join(" ".join(c) for c in chains))
    lines.append(
        "LINK times above are per route; where several routes share a link, its current "
        "travel time is the fastest of them."
    )
    return "\n".join(lines)


# --- Matching the request ------------------------------------------------------------------------

def normalise(text: str) -> str:
    """Lower case, no diacritics ("ł" too), only letters, digits and spaces."""
    text = text.lower().replace("ł", "l")
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _same_stem(word: str, token: str) -> bool:
    """``token`` (from the request) is ``word`` (from a station name) with
    another ending: at least 4 letters in common, and at most 3 of the word's
    letters at the end differ (brama/bramie, wyzynna/wyzynnej, dworzec/dworca)."""
    common = 0
    for a, b in zip(word, token):
        if a != b:
            break
        common += 1
    return common >= min(4, len(word)) and common >= len(word) - 3


# Words that describe the request, not a place (English and Polish, without
# diacritics): they must not select stations such as "Przystań" or "Stogi".
_REQUEST_WORDS = {
    "stop", "stops", "station", "stations", "close", "closed", "open", "line", "lines",
    "route", "routes", "tram", "trams", "bus", "buses", "every", "minute", "minutes",
    "twice", "slower", "faster", "between", "link", "make", "makes", "roadworks",
    "przystanek", "przystanku", "przystanki", "przystankow", "stacja", "stacji",
    "zamknij", "zamkniety", "zamknieta", "linia", "linii", "tramwaj", "tramwaju",
    "tramwaje", "autobus", "autobusu", "autobusy", "przy", "miedzy", "razy", "wolniej",
    "szybciej", "minut", "minuty", "minute", "remont", "objazd",
}
_MINUTE_WORDS = ("min", "minut", "minute")


def _request_tokens(text: str) -> list[str]:
    return normalise(text).split()


def matching_stations(graph: nx.DiGraph, text: str) -> set[str]:
    """Stations whose every longer name word appears (as a stem) in ``text``."""
    tokens = [t for t in _request_tokens(text) if len(t) >= 3 and t not in _REQUEST_WORDS and not t.isdigit()]
    found = set()
    for stop_id in graph.nodes:
        words = [w for w in normalise(graph.nodes[stop_id]["name"]).split() if len(w) >= _MIN_WORD]
        if words and all(any(_same_stem(w, t) for t in tokens) for w in words):
            found.add(stop_id)
    return found


def matching_routes(graph: nx.DiGraph, text: str) -> set[str]:
    """Routes named by id ("T8") or line number ("8", "line 199", "N1"); a number
    followed by a minutes word ("every 10 min") is a time, not a line."""
    tokens = _request_tokens(text)
    named = {
        t for i, t in enumerate(tokens)
        if not (i + 1 < len(tokens) and tokens[i + 1].startswith(_MINUTE_WORDS))
    }
    routes = set(graph.graph.get("headways", {})) | {
        r for _, _, d in graph.edges(data=True) for r in d["route_times"]
    }
    found = set()
    for route_id in routes:
        number = re.sub(r"^[A-Z]", "", route_id).lower()
        if route_id.lower() in named or (number and number in named):
            found.add(route_id)
    return found


def _referenced(changes: Iterable[ScenarioChange]) -> tuple[set[str], set[str]]:
    """Stops and routes the current changes use."""
    stops: set[str] = set()
    routes: set[str] = set()
    for change in changes:
        if isinstance(change, CloseStop):
            stops.add(change.stop_id)
        elif isinstance(change, (RemoveConnection, ChangeTravelTime)):
            stops |= {change.from_stop_id, change.to_stop_id}
        elif isinstance(change, ChangeFrequency):
            routes.add(change.route_id)
        elif isinstance(change, AddConnection):
            stops |= {change.from_stop_id, change.to_stop_id}
            routes.add(change.route_id)
        elif isinstance(change, AddStop):
            stops |= {change.from_stop_id, change.to_stop_id}
            routes.add(change.route_id)
        elif isinstance(change, AddRoute):
            stops |= set(change.stop_ids)
    return stops, routes


# --- The excerpt ---------------------------------------------------------------------------------

def describe_excerpt(graph: nx.DiGraph, text: str, current: Sequence[ScenarioChange] = ()) -> str:
    """The part of a big network that the request is about, plus every line's name."""
    stations = matching_stations(graph, text)
    named_routes = matching_routes(graph, text)
    used_stops, used_routes = _referenced(current)
    too_vague = len(stations) > _MAX_STATIONS
    if too_vague:
        stations = set()
    focus = (stations | used_stops) & set(graph.nodes)

    chains = route_chains(graph)
    shown_stops: set[str] = set(focus)
    line_texts: list[str] = []
    for route_id, route in chains.items():
        full = route_id in named_routes or route_id in used_routes
        parts = []
        for chain in route:
            stops = chain[::2]
            if full:
                keep = range(len(stops))
            else:
                hits = [i for i, s in enumerate(stops) if s in focus]
                keep = sorted({j for i in hits for j in range(max(0, i - WINDOW), min(len(stops), i + WINDOW + 1))})
            if not keep:
                continue
            # Consecutive kept stops become one piece; gaps are marked with "...".
            pieces: list[list[int]] = []
            for i in keep:
                if pieces and i == pieces[-1][-1] + 1:
                    pieces[-1].append(i)
                else:
                    pieces.append([i])
            for piece in pieces:
                tokens = chain[2 * piece[0]: 2 * piece[-1] + 1]
                prefix = "... " if piece[0] > 0 else ""
                suffix = " ..." if piece[-1] < len(stops) - 1 else ""
                parts.append(prefix + " ".join(tokens) + suffix)
                shown_stops |= {stops[i] for i in piece}
        if parts:
            line_texts.append(f"- {_route_label(graph, route_id)}: " + "; ".join(parts))

    routes_all = sorted(chains, key=lambda r: (r[0], int(re.sub(r"\D", "", r) or 0), r))
    headways: dict[str, float] = graph.graph.get("headways", {})
    lines = [
        f"NETWORK EXCERPT: the network has {graph.number_of_nodes()} stops and {len(chains)} "
        "routes; only the part this request is about is listed below. If the user means a stop "
        "or link that is not listed, answer \"unclear\" and ask them to name the stop exactly "
        "as it appears on the map.",
    ]
    if too_vague:
        lines.append("(The request matched too many stops to list them: ask which stop is meant.)")
    lines += ["", "STOPS (id: name):"]
    lines += [f"- {s}: {graph.nodes[s]['name']}" for s in sorted(shown_stops)] or ["(none matched)"]
    lines += ["", LINES_LEGEND + " \"...\": the line continues (not listed)."]
    lines += line_texts or ["(no line through the matched stops)"]
    lines += [
        "",
        "ALL ROUTES (id, minutes between buses): "
        + ", ".join(f"{r} {headways[r]:g}" if r in headways else r for r in routes_all),
    ]
    return "\n".join(lines)
