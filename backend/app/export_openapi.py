"""Write the API's OpenAPI schema to a JSON file.

The frontend generates its TypeScript types from this file
(`npm run gen:types` in frontend/), so the two never drift apart.

Run from the backend/ folder:
    python -m app.export_openapi                  # writes ../frontend/openapi.json
    python -m app.export_openapi path/to/out.json

No running server, database or API key is needed: the schema is read
straight from the FastAPI app object.
"""

import json
import sys
from pathlib import Path

from app.main import app

DEFAULT_OUTPUT = Path(__file__).resolve().parents[2] / "frontend" / "openapi.json"


def export_openapi(output: Path) -> None:
    """Serialise the schema deterministically (stable diffs for the CI check)."""
    schema = app.openapi()
    output.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT
    export_openapi(output)
    print(f"OpenAPI schema written to {output}")


if __name__ == "__main__":
    main()
