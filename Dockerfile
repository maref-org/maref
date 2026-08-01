# ──────────────────────────────────────────────────────
# Stage 1: Builder — install dependencies
# ──────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY pyproject.toml README.md LICENSE ./
COPY src/ src/

# Install into a virtualenv for easy copying
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir ".[all,desktop,identity]"
RUN playwright install chromium --with-deps 2>/dev/null || true

# ──────────────────────────────────────────────────────
# Stage 2: Runtime — minimal image
# ──────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="MAREF Desktop Agent"
LABEL org.opencontainers.image.description="Multi-Agent Recursive Engineering Framework — Desktop Agent"
LABEL org.opencontainers.image.version="0.43.0"
LABEL org.opencontainers.image.licenses="Apache-2.0"

ENV DEBIAN_FRONTEND=noninteractive

# Runtime system dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    x11-utils \
    scrot \
    libgl1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r maref && useradd -r -g maref -d /app -s /sbin/nologin maref

WORKDIR /app

# Copy virtualenv from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create necessary directories with correct ownership
RUN mkdir -p /app/data /app/logs /app/research_output && \
    chown -R maref:maref /app

# Switch to non-root user
USER maref

ENV MAREF_DRY_RUN=false
ENV DISPLAY=:99
ENV PYTHONUNBUFFERED=1
ENV HOME=/app

EXPOSE 8080 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "from maref.desktop import DesktopAgent; print('OK')" || exit 1

ENTRYPOINT ["maref"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8080"]
