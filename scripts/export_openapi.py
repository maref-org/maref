#!/usr/bin/env python3
"""导出 Sidecar FastAPI 应用 OpenAPI schema。"""
from __future__ import annotations

import json
import sys

try:
    from sidecar.server import create_app

    app = create_app()
    schema = app.openapi()
    schema["info"]["version"] = "0.30.0"
    with open("gui/openapi-schema.json", "w") as f:
        json.dump(schema, f, indent=2)
    paths = len(schema.get("paths", {}))
    print(f"Exported OpenAPI schema: {paths} paths")
except ImportError:
    print("Warning: sidecar package not available, using cached schema", file=sys.stderr)
    import shutil

    shutil.copy("gui/openapi-schema-cached.json", "gui/openapi-schema.json")
