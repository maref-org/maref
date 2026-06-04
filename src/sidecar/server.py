from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from maref.observability.security_headers_middleware import SecurityHeadersMiddleware


def create_app(obs_bridge: Any = None) -> FastAPI:
    app = FastAPI(
        title="MAREF Sidecar",
        version="0.30.0-GA",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:8080"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/health")
    async def health():
        return {"status": "ok", "version": "0.30.0-GA"}

    @app.get("/metrics")
    async def metrics():
        prometheus_text = "# MAREF Sidecar metrics\n"
        return Response(content=prometheus_text, media_type="text/plain; version=0.0.4")

    return app
