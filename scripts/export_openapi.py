#!/usr/bin/env python3
"""Export MAREF Sidecar OpenAPI schema for frontend TypeScript type generation.

Usage:
    python scripts/export_openapi.py

Output:
    gui/openapi-schema.json

Then run:
    cd gui && pnpm exec openapi-typescript openapi-schema.json -o src/types/api.d.ts
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sidecar.server import create_app


def export_openapi(output_path: Path | None = None) -> Path:
    """Generate and export OpenAPI schema from FastAPI app."""
    app = create_app()
    openapi_schema = app.openapi()

    if output_path is None:
        output_path = Path(__file__).parent.parent / "gui" / "openapi-schema.json"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(openapi_schema, f, indent=2, ensure_ascii=False)

    print(f"OpenAPI schema exported to: {output_path}")
    print(f"  API version: {openapi_schema.get('info', {}).get('version', 'unknown')}")
    print(f"  Paths: {len(openapi_schema.get('paths', {}))}")
    print(f"  Components: {len(openapi_schema.get('components', {}).get('schemas', {}))}")

    return output_path


if __name__ == "__main__":
    output = export_openapi()
    print(f"\nNext step: cd gui && pnpm exec openapi-typescript openapi-schema.json -o src/types/api.d.ts")
