"""CSV export of every changed journey (moved from the browser in Day 14:
a city's result lists only the largest changes, so the full list comes from here).

Same file as before: one row per changed journey in the results table's order,
values exactly as computed, written as the browser wrote them ("4", not "4.0"),
RFC 4180 quoting, CRLF line endings. The browser adds the BOM for Excel.
"""

from collections.abc import Sequence

from app.schemas.simulation import JourneyChange
from app.services.simulation_service import table_order

CSV_COLUMNS = (
    "origin_id",
    "origin_name",
    "destination_id",
    "destination_name",
    "status",
    "time_before_min",
    "time_after_min",
    "change_min",
)


def _number(value: float | None) -> str:
    """Like JavaScript's String(number): 4.0 -> "4", 4.5 -> "4.5"."""
    if value is None:
        return ""  # impossible journeys have no "after" time
    return str(int(value)) if value.is_integer() else repr(value)


def _field(text: str) -> str:
    """Quote a field when it contains a comma, quote or line break (RFC 4180)."""
    if any(c in text for c in ',"\r\n'):
        return '"' + text.replace('"', '""') + '"'
    return text


def changed_journeys_csv(journeys: Sequence[JourneyChange], names: dict[str, str]) -> str:
    rows = [
        ",".join(_field(value) for value in (
            j.origin_id,
            names.get(j.origin_id, j.origin_id),
            j.destination_id,
            names.get(j.destination_id, j.destination_id),
            j.status,
            _number(j.time_before_min),
            _number(j.time_after_min),
            _number(j.change_min),
        ))
        for j in table_order(journeys)
    ]
    return "\r\n".join([",".join(CSV_COLUMNS), *rows]) + "\r\n"
