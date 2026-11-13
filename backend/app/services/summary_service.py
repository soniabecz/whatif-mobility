"""AI summary of simulation results (Day 12, part 2). Kept apart from the simulation.

Safeguard: the language model never writes a number. It gets a FACT SHEET of
computed values, each with a placeholder name, and writes text such as
"{slower} journeys get slower". The backend checks the text and then inserts
the values itself, formatted as the results panel shows them. A text is
rejected if it contains a digit (outside ids such as R5 or N1), an unknown
placeholder, or a number or ratio word ("two", "twice", "half"). After one
rejected attempt the model gets one retry; then the summary is withheld.

This proves that every number comes from the results. It cannot prove that a
sentence uses the right one (e.g. {slower} where "faster" was meant); the
placeholder names make that unlikely, and the UI asks the user to check.
"""

import json
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass

import networkx as nx
from pydantic import ValidationError

from app.schemas.ai import AISummary, SummaryResponse, strict_json_schema
from app.schemas.scenario import (
    AddConnection,
    AddRoute,
    AddStop,
    ChangeFrequency,
    ChangeTravelTime,
    ScenarioChange,
)
from app.schemas.simulation import SimulationResult
from app.services.ai_service import AIOutputError, ChatModel, describe_current_changes

logger = logging.getLogger(__name__)

_OUTPUT_SCHEMA = strict_json_schema(AISummary)
MAX_SUMMARY_CHARS = 1200
MAX_ATTEMPTS = 2

_PLACEHOLDER = re.compile(r"\{([a-z0-9_]+)\}")
# Ids of stops and routes (R5, N1, CEN): letters then digits, as one word.
_ID = re.compile(r"\b[A-Z]{1,3}\d+\b")
_DIGITS = re.compile(r"\d+(?:[.,]\d+)?")
_NUMBER_WORDS = re.compile(
    r"\b(two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|"
    r"fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|"
    r"seventy|eighty|ninety|hundreds?|thousands?|millions?|dozens?|half|halves|halved|"
    r"twice|double|doubled|doubles|triple|tripled|quadruple|quarter|quarters|thirds?)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Fact:
    key: str
    value: str  # formatted exactly as inserted
    description: str


# --- Fact sheet -----------------------------------------------------------------------

def _minutes(value: float) -> str:
    return f"{value:.1f}"


def _direction(value: float, more: str, less: str) -> str:
    return more if value > 0 else less if value < 0 else "no change"


def build_facts(
    result: SimulationResult, stop_names: dict[str, str], equal_demand: bool = False
) -> list[Fact]:
    """Every number the summary may use, from the result and the change list.

    ``equal_demand``: every stop has the same activity level (a real network
    without passenger data), so the "demand-weighted" shares are plain shares."""
    s = result.summary
    facts = [
        Fact("total_journeys", str(s.total_journeys), "journeys compared: every pair of stops, both ways"),
        Fact("unchanged", str(s.unchanged), "journeys with an unchanged time"),
        Fact("slower", str(s.slower), "journeys that get slower"),
        Fact("faster", str(s.faster), "journeys that get faster"),
        Fact("impossible", str(s.impossible), "journeys no longer possible"),
    ]
    if s.newly_possible:
        facts.append(Fact("newly_possible", str(s.newly_possible), "journeys impossible before, possible now"))
    if s.to_or_from_closed_stop:
        facts.append(Fact("closed_excluded", str(s.to_or_from_closed_stop),
                          "journeys to or from a closed stop, left out of all figures"))
    if s.walked_to_or_from_closed_stop:
        facts.append(Fact("walked", str(s.walked_to_or_from_closed_stop),
                          "journeys to or from a closed stop where passengers walk to a nearby stop"))
    if s.average_time_before_min is not None and s.average_time_after_min is not None:
        change = s.average_time_after_min - s.average_time_before_min
        facts += [
            Fact("avg_before", _minutes(s.average_time_before_min), "average journey time before, minutes"),
            Fact("avg_after", _minutes(s.average_time_after_min), "average journey time after, minutes"),
            Fact("avg_change", _minutes(abs(change)),
                 f"minutes the average journey gets {_direction(change, 'longer', 'shorter')}"),
        ]
    facts.append(Fact("total_change", _minutes(abs(s.total_time_change_min)),
                      f"minutes all compared journeys together get "
                      f"{_direction(s.total_time_change_min, 'longer', 'shorter')}"))
    if s.largest_increase and s.largest_increase.change_min is not None:
        j = s.largest_increase
        route = f"{stop_names.get(j.origin_id, j.origin_id)} to {stop_names.get(j.destination_id, j.destination_id)}"
        facts += [
            Fact("largest_increase", _minutes(j.change_min), f"largest increase, minutes: {route}"),
            Fact("largest_increase_before", _minutes(j.time_before_min), f"{route} before, minutes"),
            Fact("largest_increase_after", _minutes(j.time_after_min or 0.0), f"{route} after, minutes"),
        ]
    impacts = {impact.stop_id: impact for impact in result.stop_impacts}
    for rank, stop_id in enumerate(result.most_affected_stop_ids, start=1):
        impact = impacts[stop_id]
        name = stop_names.get(stop_id, stop_id)
        closed = " (closed)" if impact.closed else ""
        facts += [
            Fact(f"stop{rank}_affected", str(impact.affected_journeys),
                 f"most affected stop no. {rank}: {name}{closed}; journeys to or from it that change"),
            Fact(f"stop{rank}_impossible", str(impact.impossible_journeys),
                 f"{name}: journeys to or from it no longer possible"),
        ]
        if impact.average_change_min is not None:
            facts.append(Fact(f"stop{rank}_avg_change", _minutes(abs(impact.average_change_min)),
                              f"{name}: minutes its changed journeys get "
                              f"{_direction(impact.average_change_min, 'longer', 'shorter')} on average"))
    if s.new_stops:
        n = s.new_stops
        facts += [
            Fact("new_stop_journeys", str(n.journeys), "journeys to or from new stops (no before to compare)"),
            Fact("new_stop_possible", str(n.possible), "of these, possible"),
        ]
        if n.average_time_min is not None:
            facts.append(Fact("new_stop_avg", _minutes(n.average_time_min),
                              "average time of the possible new-stop journeys, minutes"))
    d = s.demand_weighted
    for key, value, what in (
        ("demand_slower_pct", d.slower_pct, "slower"),
        ("demand_faster_pct", d.faster_pct, "faster"),
        ("demand_impossible_pct", d.impossible_pct, "no longer possible"),
    ):
        weighting = (
            "every stop weighs the same (no passenger data)" if equal_demand
            else "weighted by INVENTED demand (say so if used)"
        )
        facts.append(Fact(key, _minutes(value), f"percent of trips {what}; {weighting}"))
    if s.transfer_penalty_min:
        facts.append(Fact("transfer_penalty", _minutes(s.transfer_penalty_min),
                          "minutes counted for every change of bus (a setting)"))
    facts += _input_facts(result.scenario.changes)
    return facts


def _input_facts(changes: Sequence[ScenarioChange]) -> list[Fact]:
    """Numbers the user entered in the change list (they may be mentioned too)."""
    facts: list[Fact] = []
    for number, change in enumerate(changes, start=1):
        if isinstance(change, (ChangeTravelTime, AddConnection)):
            facts.append(Fact(f"change{number}_minutes", f"{change.travel_time_min:g}",
                              f"change {number}: the travel time set, minutes"))
        elif isinstance(change, (ChangeFrequency, AddRoute)):
            facts.append(Fact(f"change{number}_headway", f"{change.headway_min:g}",
                              f"change {number}: minutes between buses"))
        elif isinstance(change, AddStop):
            facts += [
                Fact(f"change{number}_minutes_in", f"{change.time_from_min:g}",
                     f"change {number}: minutes to the new stop"),
                Fact(f"change{number}_minutes_out", f"{change.time_to_min:g}",
                     f"change {number}: minutes from the new stop on"),
            ]
    return facts


# --- Checking and filling ---------------------------------------------------------------

def check_summary(text: str, facts: Sequence[Fact]) -> list[str]:
    """Problems with the model's text (empty = acceptable)."""
    problems: list[str] = []
    if not text.strip():
        return ["the summary is empty"]
    if len(text) > MAX_SUMMARY_CHARS:
        problems.append(f"the summary is longer than {MAX_SUMMARY_CHARS} characters")
    known = {fact.key for fact in facts}
    unknown = sorted({key for key in _PLACEHOLDER.findall(text) if key not in known})
    if unknown:
        problems.append("unknown placeholders: " + ", ".join(f"{{{key}}}" for key in unknown))
    rest = _ID.sub("", _PLACEHOLDER.sub("", text))
    if "{" in rest or "}" in rest:
        problems.append("braces outside a placeholder")
    digits = _DIGITS.findall(rest)
    if digits:
        problems.append("numbers written directly: " + ", ".join(dict.fromkeys(digits)))
    words = _NUMBER_WORDS.findall(rest)
    if words:
        problems.append("number or ratio words: " + ", ".join(dict.fromkeys(w.lower() for w in words)))
    return problems


def fill_summary(text: str, facts: Sequence[Fact]) -> str:
    values = {fact.key: fact.value for fact in facts}
    return _PLACEHOLDER.sub(lambda match: values[match.group(1)], text).strip()


# --- Prompt and the call ------------------------------------------------------------------

def build_summary_prompt(baseline: nx.DiGraph, result: SimulationResult, facts: Sequence[Fact]) -> str:
    fact_lines = "\n".join(f"- {{{fact.key}}} = {fact.value}: {fact.description}" for fact in facts)
    settings = (
        f"waiting for the bus is {'included' if result.summary.include_waiting else 'not included'}"
    )
    return f"""You write a short summary of the computed results of a bus network \
simulation for a non-expert. You never compute, estimate or invent anything.

How numbers work: you NEVER write a number yourself. Every quantity comes from \
the FACTS below and is written as its placeholder, e.g. "{{slower}} journeys get \
slower". The placeholder is replaced by its value later. Rules:
- No digits at all, except inside stop or route ids such as R5 or N1.
- No number words ("two", "ten", "hundred") and no ratios ("half", "twice", \
"double"). Comparisons only in words such as "most", "fewer", "longer".
- Use only placeholders from FACTS, each exactly as written, and use each one \
only for what its description says.
- Write minutes as "{{avg_before}} min" and percentages as "{{demand_slower_pct}}%".

Content: 3 or 4 short sentences of plain English (about 80 words; never more \
than {MAX_SUMMARY_CHARS} characters). Start with the overall effect, then the \
most affected stops (at most three) and the largest increase if there is one. \
Style: the values are exact, so never write "about" or "roughly" before a \
placeholder; say "none" instead of using a placeholder whose value is 0; do not \
repeat a figure already given (no "(30 trips)" after "30 journeys"); if a \
before and after value are equal, say the value once and that it is unchanged; \
group stops only when their figures are the same. Mention journeys to or from closed or new \
stops only if those facts exist. Percentages of trips: follow what their \
description says about demand. No advice, no causes or effects beyond the listed changes, \
no headings, no lists. Settings: {settings}.

{describe_current_changes(baseline, list(result.scenario.changes))}

FACTS (placeholder = value: meaning):
{fact_lines}
"""


def summarise(baseline: nx.DiGraph, result: SimulationResult, model: ChatModel) -> SummaryResponse:
    """Ask the model for a summary of ``result``; check it, retry once, fill in the values."""
    stop_names = {stop_id: baseline.nodes[stop_id]["name"] for stop_id in baseline.nodes}
    for change in result.scenario.changes:
        if isinstance(change, AddStop):
            stop_names[change.stop_id] = change.name
    equal_demand = len({baseline.nodes[s].get("activity", 1) for s in baseline.nodes}) <= 1
    facts = build_facts(result, stop_names, equal_demand)
    prompt = build_summary_prompt(baseline, result, facts)

    request = "Summarise these results."
    problems: list[str] = []
    for _ in range(MAX_ATTEMPTS):
        raw = model.complete_json(prompt, request, _OUTPUT_SCHEMA)
        try:
            text = AISummary.model_validate(json.loads(raw)).summary
        except (json.JSONDecodeError, ValidationError) as error:
            logger.warning("AI summary did not match the schema: %s", error)
            raise AIOutputError("The AI returned an answer in an unexpected format.") from error
        problems = check_summary(text, facts)
        if not problems:
            return SummaryResponse(status="ok", summary=fill_summary(text, facts), message="")
        logger.info("AI summary rejected: %s", "; ".join(problems))
        request = (
            "Your previous summary was rejected because it broke the rules ("
            + "; ".join(problems)
            + "). Write it again, using placeholders from FACTS for every number."
        )
    return SummaryResponse(
        status="withheld",
        summary=None,
        message="The AI summary was withheld because it did not stick to the computed "
        "figures (" + "; ".join(problems) + "). The results above are complete without it.",
    )
