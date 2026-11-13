"""Natural language -> scenario (Day 5). Kept separate from the simulation.

The language model only TRANSLATES the user's text into the scenario format.
It never sees or produces simulation results. Its answer is checked three times:
  1. Groq strict structured outputs force the JSON shape (AIInterpretation);
  2. the changes are validated with the Day 3 Scenario schema;
  3. a dry run applies them to a copy of the baseline graph (no metrics), so
     unknown stops or missing links are caught before the user sees them.
Any problem with the *content* becomes status "unclear" with a message;
problems with the *provider* raise AIServiceError subclasses.
"""

import json
import logging
from collections.abc import Sequence
from functools import lru_cache
from typing import Protocol

import groq
import networkx as nx
from pydantic import TypeAdapter, ValidationError

from app.schemas.ai import AIInterpretation, InterpretResponse, strict_json_schema
from app.schemas.scenario import (
    MAX_CHANGES,
    MAX_HEADWAY_MIN,
    MAX_ROUTE_STOPS,
    MIN_HEADWAY_MIN,
    NEW_ROUTE_COLORS,
    AddConnection,
    AddRoute,
    AddStop,
    ChangeFrequency,
    ChangeTravelTime,
    CloseStop,
    RemoveConnection,
    Scenario,
    ScenarioChange,
)
from app.services.simulation_service import ScenarioError, apply_scenario

logger = logging.getLogger(__name__)

_SCHEMA_NAME = "scenario_interpretation"
_OUTPUT_SCHEMA = strict_json_schema(AIInterpretation)
# Generous: gpt-oss reasoning tokens count towards this limit too.
_MAX_COMPLETION_TOKENS = 8192


class AIServiceError(Exception):
    """Base class: the AI could not produce an answer."""


class AINotConfiguredError(AIServiceError):
    """No API key configured."""


class AIUnavailableError(AIServiceError):
    """Provider unreachable, too slow, rate-limited or rejecting the key."""


class AIOutputError(AIServiceError):
    """The provider answered, but not with usable JSON."""


class InvalidChangeListError(ValueError):
    """The current change list sent with the request does not fit the network."""


_CHANGES_ADAPTER = TypeAdapter(list[ScenarioChange])


class ChatModel(Protocol):
    """The only thing ai_service needs from a language model. Tests pass a fake."""

    def complete_json(self, system_prompt: str, user_text: str, schema: dict) -> str:
        """Return the model's raw JSON answer matching ``schema``."""
        ...


# --- Groq implementation ------------------------------------------------------

class GroqChatModel:
    def __init__(self, api_key: str, model: str, timeout_seconds: float) -> None:
        self._client = groq.Groq(api_key=api_key, timeout=timeout_seconds, max_retries=1)
        self._model = model

    def complete_json(self, system_prompt: str, user_text: str, schema: dict) -> str:
        try:
            completion = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_text},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": _SCHEMA_NAME, "strict": True, "schema": schema},
                },
                reasoning_effort="medium",
                include_reasoning=False,
                max_completion_tokens=_MAX_COMPLETION_TOKENS,
            )
        # Most specific first: APITimeoutError is a subclass of APIConnectionError.
        except groq.AuthenticationError as error:
            raise AIUnavailableError(
                "The AI provider rejected the API key. Check GROQ_API_KEY in backend/.env."
            ) from error
        except groq.RateLimitError as error:
            raise AIUnavailableError(
                "The AI rate limit was reached. Please wait a minute and try again."
            ) from error
        except groq.APITimeoutError as error:
            raise AIUnavailableError("The AI took too long to answer. Please try again.") from error
        except groq.APIConnectionError as error:
            raise AIUnavailableError("Could not reach the AI provider.") from error
        except groq.APIStatusError as error:
            logger.warning("Groq returned HTTP %s: %s", error.status_code, error.message)
            raise AIUnavailableError(
                f"The AI provider returned an error (HTTP {error.status_code})."
            ) from error

        if not completion.choices:
            raise AIOutputError("The AI returned no answer.")
        choice = completion.choices[0]
        if choice.finish_reason == "length":
            raise AIOutputError("The AI answer was cut off. Please try a shorter request.")
        if not choice.message.content:
            raise AIOutputError("The AI returned an empty answer.")
        return choice.message.content


@lru_cache(maxsize=4)
def get_groq_model(api_key: str, model: str, timeout_seconds: float) -> GroqChatModel:
    """Reuse one client (and its HTTP connection pool) per configuration."""
    return GroqChatModel(api_key, model, timeout_seconds)


# --- Prompt -------------------------------------------------------------------

def describe_network(graph: nx.DiGraph) -> str:
    """Plain-text network description for the prompt (deterministic order)."""
    lines = ["STOPS (id: name):"]
    for stop_id in sorted(graph.nodes):
        lines.append(f"- {stop_id}: {graph.nodes[stop_id]['name']}")

    headways: dict[str, float] = graph.graph.get("headways", {})
    names: dict[str, str] = graph.graph.get("route_names", {})
    served: dict[str, set[str]] = {}
    for u, v, edge in graph.edges(data=True):
        for route_id in edge["routes"]:
            served.setdefault(route_id, set()).update((u, v))
    if headways:
        lines.append("")
        lines.append("ROUTES (id: name, current headway = minutes between buses; stops served):")
        for route_id in sorted(headways):
            name = names.get(route_id, route_id)
            stops = ", ".join(sorted(served.get(route_id, set())))
            lines.append(
                f"- {route_id}: {name}, a bus every {headways[route_id]:g} min; stops: {stops}"
            )

    lines.append("")
    lines.append("LINKS between directly connected stops (current fastest travel time):")
    for a, b in sorted({tuple(sorted(edge)) for edge in graph.edges}):
        forward = graph.edges[a, b] if graph.has_edge(a, b) else None
        backward = graph.edges[b, a] if graph.has_edge(b, a) else None
        if forward and backward and forward["weight"] == backward["weight"]:
            routes = ", ".join(forward["routes"])
            lines.append(f"- {a} <-> {b}: {forward['weight']:g} min (routes {routes})")
            continue
        for u, v, edge in ((a, b, forward), (b, a, backward)):
            if edge:
                lines.append(
                    f"- {u} -> {v} (one way): {edge['weight']:g} min "
                    f"(routes {', '.join(edge['routes'])})"
                )
    return "\n".join(lines)


def describe_change(change: ScenarioChange, names: dict[str, str]) -> str:
    """One change in plain words with ids, for the prompt's CURRENT CHANGES."""
    def stop(stop_id: str) -> str:
        return f"{names.get(stop_id, stop_id)} ({stop_id})"

    def link(a: str, b: str, both: bool) -> str:
        return f"{stop(a)} {'<->' if both else '->'} {stop(b)}"

    if isinstance(change, CloseStop):
        return f"close_stop: {stop(change.stop_id)}"
    if isinstance(change, RemoveConnection):
        return f"remove_connection: {link(change.from_stop_id, change.to_stop_id, change.both_directions)}"
    if isinstance(change, ChangeTravelTime):
        return (
            f"change_travel_time: {link(change.from_stop_id, change.to_stop_id, change.both_directions)}"
            f" now {change.travel_time_min:g} min"
        )
    if isinstance(change, ChangeFrequency):
        return f"change_frequency: route {change.route_id} a bus every {change.headway_min:g} min"
    if isinstance(change, AddConnection):
        return (
            f"add_connection: route {change.route_id} also runs "
            f"{link(change.from_stop_id, change.to_stop_id, change.both_directions)}"
            f" in {change.travel_time_min:g} min"
        )
    if isinstance(change, AddStop):
        return (
            f"add_stop: NEW stop {change.stop_id} \"{change.name}\" on route {change.route_id}, "
            f"{stop(change.from_stop_id)} {change.time_from_min:g} min -> {change.stop_id} "
            f"{change.time_to_min:g} min -> {stop(change.to_stop_id)}"
        )
    if isinstance(change, AddRoute):
        stops = [*change.stop_ids, change.stop_ids[0]] if change.is_loop else change.stop_ids
        times = " + ".join(f"{t:g}" for t in change.travel_times_min)
        return (
            f"add_route: NEW route {change.route_id} \"{change.name}\" ({change.color}), a bus every "
            f"{change.headway_min:g} min, {'loop, ' if change.is_loop else ''}"
            f"{'both directions' if change.both_directions else 'one way'}: "
            f"{' -> '.join(stop(s) for s in stops)} ({times} min)"
        )
    raise ValueError(f"unknown change type: {change!r}")  # pragma: no cover


def describe_current_changes(graph: nx.DiGraph, current: Sequence[ScenarioChange]) -> str:
    """The user's current change list, numbered as the user sees it."""
    if not current:
        return "CURRENT CHANGES: none yet."
    names = {stop_id: graph.nodes[stop_id]["name"] for stop_id in graph.nodes}
    lines = ["CURRENT CHANGES (the user's list, numbered; applied in this order):"]
    for number, change in enumerate(current, start=1):
        if isinstance(change, AddStop):
            names[change.stop_id] = change.name  # later changes may use the new stop
        lines.append(f"{number}. {describe_change(change, names)}")
    return "\n".join(lines)


def describe_new_route_defaults(graph: nx.DiGraph, current: Sequence[ScenarioChange] = ()) -> str:
    """Display-only values for a new route: the next free id and unused colours
    (routes added by the current change list count as used)."""
    added = [change for change in current if isinstance(change, AddRoute)]
    used_ids = (
        set(graph.graph.get("headways", {}))
        | set(graph.graph.get("route_names", {}))
        | {change.route_id for change in added}
    )
    number = 1
    while f"R{number}" in used_ids:
        number += 1
    used_colors = {c.lower() for c in graph.graph.get("route_colors", {}).values()}
    used_colors |= {change.color.lower() for change in added}
    free = [c for c in NEW_ROUTE_COLORS if c not in used_colors] or list(NEW_ROUTE_COLORS)
    return (
        f"NEW ROUTES: use route_id R{number} (R{number + 1}, ... for further ones) "
        f"and a colour from: {', '.join(free)} (a different one per new route)."
    )


def build_system_prompt(graph: nx.DiGraph, current: Sequence[ScenarioChange] = ()) -> str:
    return f"""You translate a user's description of hypothetical changes to a city bus \
network into a structured scenario. You only translate; you never estimate or \
describe the impact of the changes (a separate simulation computes all results).

The user is building a list of changes (CURRENT CHANGES below). You never \
rewrite that list; you answer with operations on it:
- remove_numbers: numbers of current changes to remove ("undo the last one", \
"forget the closure").
- replace: {{number, change}} to change a current change in place ("make that \
8 minutes instead"). Prefer replacing over adding a second change to the same \
stop, link or route.
- changes: new changes, appended at the end ("and also ...").
Leave an operation empty when it is not needed. Never remove or replace a \
change the user did not ask about.

The six possible change types:
- close_stop: a stop is closed (buses drive through without stopping). Needs stop_id.
- remove_connection: the link between two DIRECTLY connected stops disappears.
- change_travel_time: a link between two DIRECTLY connected stops gets a new \
travel time in minutes (travel_time_min, greater than 0, at most 600).
- change_frequency: a route runs more or less often. Needs route_id and \
headway_min = minutes between two buses ({MIN_HEADWAY_MIN} to {MAX_HEADWAY_MIN}).
- add_connection: an existing route also runs directly between two stops (an \
extension or a shortcut). Needs route_id, from_stop_id, to_stop_id, \
travel_time_min and both_directions. At least one of the two stops must already \
be served by that route (see ROUTES), the stops must differ, and the route must \
not already run between them. The user must give the travel time; never guess \
it: without one the request is unclear.
- add_route: a new bus line through existing stops in order. Needs route_id, \
name, color, headway_min, stop_ids (2 to {MAX_ROUTE_STOPS} different stops, \
in the order the bus calls), travel_times_min (one per stretch between \
consecutive stops; if is_loop, one more for the way from the last stop back \
to the first), is_loop and both_directions. Stops do not need to be directly \
linked today. The user must give the stops in order, EVERY travel time and the \
headway; never guess any of them: if one is missing the request is unclear, \
and the message asks only for what is missing, in plain words (never for \
route_id, color, name or field names: you choose those). Take the name from \
the user's words, or "New line" plus the route id; route_id and color as in \
NEW ROUTES below; is_loop only if the user says the bus returns to the first \
stop (a ring or loop).

Rules:
- Use only stop ids from the list below, or stops added by a current change \
(NEW stop). Routes added by a current change (NEW route) can be used like \
the others. Match names flexibly ("the airport" = AIR).
- Link changes are only possible between stops listed together under LINKS. \
A request about stops that are not directly linked is unclear.
- both_directions is true unless the user clearly means one direction only.
- For relative requests ("twice as slow", "5 minutes longer", "halve the time") \
compute the new absolute time from the current time listed below, rounded to \
one decimal. If a current change already sets that link's time (or a route's \
headway), start from that value and replace that change.
- Frequencies are given as a headway: "every 5 minutes" = 5; "12 buses an hour" \
= 60 / 12 = 5; "twice as often" = half the current headway listed below; \
"half as often" = double it. Round to one decimal. Routes are named by id \
("R3"), name ("the ring") or line number ("line 3").
- New stops cannot be added here (that needs a position on the map): answer \
"unclear" and tell the user to place the stop on the map with the "Add stop" tab \
of the form.
- At most {MAX_CHANGES} changes in the list after your operations.
- If the request is ambiguous, refers to something not in the network, asks \
for something other than these six change types (for example new stops), or \
is not about changing the network: status "unclear", no \
changes, and a short message that explains why or asks a clarifying question.
- Otherwise status "ok" and a one-sentence message summarising what you \
did (removed, changed, added), using stop names.
- Write the message in the language of the user's request.

{describe_network(graph)}

{describe_new_route_defaults(graph, current)}

{describe_current_changes(graph, current)}
"""


# --- Interpretation -----------------------------------------------------------

def _unclear(message: str) -> InterpretResponse:
    return InterpretResponse(status="unclear", changes=[], message=message)


def _check_current(baseline: nx.DiGraph, current: list[ScenarioChange]) -> None:
    if not current:
        return
    try:
        apply_scenario(baseline, Scenario(changes=current))
    except ScenarioError as error:
        raise InvalidChangeListError(f"The current change list does not fit the network: {error}.") from None


def interpret(
    text: str,
    baseline: nx.DiGraph,
    model: ChatModel,
    current: list[ScenarioChange] | None = None,
) -> InterpretResponse:
    """Apply the user's request to the current change list (empty = a new list).

    Returns the complete new list, validated against ``baseline``.
    Raises InvalidChangeListError if ``current`` itself does not fit the network.
    """
    current = list(current or [])
    _check_current(baseline, current)
    raw = model.complete_json(build_system_prompt(baseline, current), text, _OUTPUT_SCHEMA)

    try:
        interpretation = AIInterpretation.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValidationError) as error:
        logger.warning("AI answer did not match the schema: %s", error)
        raise AIOutputError("The AI returned an answer in an unexpected format.") from error

    message = interpretation.message.strip()
    removed = sorted(interpretation.remove_numbers)
    replaced = sorted(r.number for r in interpretation.replace)
    if interpretation.status == "unclear" or not (removed or replaced or interpretation.changes):
        return _unclear(message or "Sorry, I could not turn that into a network change.")

    # The numbers must exist in the current list, each used once.
    numbers = removed + replaced
    if len(set(numbers)) != len(numbers):
        return _unclear("The suggestion uses the same change twice. Please rephrase.")
    unknown = [n for n in numbers if not 1 <= n <= len(current)]
    if unknown:
        size = f"only {len(current)}" if current else "no"
        return _unclear(f"The suggestion refers to change {unknown[0]}, but the list has {size} changes.")

    try:
        replacements = dict(
            zip(
                (r.number for r in interpretation.replace),
                _CHANGES_ADAPTER.validate_python([r.change.model_dump() for r in interpretation.replace]),
                strict=True,
            )
        )
        added = _CHANGES_ADAPTER.validate_python([c.model_dump() for c in interpretation.changes])
    except ValidationError as error:
        first = error.errors()[0]
        return _unclear(f"The suggested change is not valid ({first['msg'].lower()}).")

    changes = [
        replacements.get(number, change)
        for number, change in enumerate(current, start=1)
        if number not in removed
    ] + added
    if len(changes) > MAX_CHANGES:
        return _unclear(
            f"That would make {len(changes)} changes; a scenario can have at most {MAX_CHANGES}."
        )
    if changes:
        try:
            apply_scenario(baseline, Scenario(changes=changes))  # dry run on a copy
        except ScenarioError as error:
            return _unclear(f"The resulting list does not fit the network: {error}.")

    return InterpretResponse(
        status="ok", changes=changes, removed=removed, replaced=replaced, added=len(added),
        message=message,
    )
