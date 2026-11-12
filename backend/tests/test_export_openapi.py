"""The OpenAPI export feeds the frontend's generated TypeScript types."""

import json
from pathlib import Path

from app.export_openapi import export_openapi
from app.main import app


def test_export_writes_the_app_schema(tmp_path: Path) -> None:
    output = tmp_path / "openapi.json"
    export_openapi(output)

    written = json.loads(output.read_text(encoding="utf-8"))
    assert written == app.openapi()
    for name in ("Scenario", "SimulationResult", "JourneyComparison", "NetworkOut"):
        assert name in written["components"]["schemas"]


def test_export_is_deterministic(tmp_path: Path) -> None:
    # The CI check compares regenerated files byte for byte.
    first, second = tmp_path / "a.json", tmp_path / "b.json"
    export_openapi(first)
    export_openapi(second)
    assert first.read_bytes() == second.read_bytes()
    assert first.read_text(encoding="utf-8").endswith("}\n")
