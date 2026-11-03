# ──────────────────────────────────────────────────────
# Stage 1: Builder — install dependencies
# ──────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY pyproject.toml README.md LICENSE ./
COPY src/ src/

# Install into a virtualenv for easy copying
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip
# GHSA-9v8h-qqgm-4m35 (brotli 解码器越界写, CVSS 4.0 远程 RCE) 修复版本 1.2.1,
# 但 mitmproxy 12.3.0 硬约束 Brotli<=1.2.0 且无更高版本放宽。brotli 与 mitmproxy
# 之间仅为稳定的解压 API, 1.2.1 是同一 API 的安全补丁, 故 --no-deps 覆盖 pin。
# mitmproxy 放开约束后应移除本条, 改回由依赖解析器升级。
RUN pip install --no-cache-dir ".[all,desktop,identity]" \
    && pip install --no-cache-dir --upgrade "msgpack>=1.2.1" "tornado>=6.5.6" "setuptools>=78.1.1" \
    && pip install --no-cache-dir --no-deps --force-reinstall "brotli>=1.2.1" \
    && pip uninstall -y wandb \
    && rm -f /opt/venv/lib/python3.12/site-packages/pip/_vendor/vendor.txt \
          /opt/venv/lib/python3.12/site-packages/pip/_vendor/bom.cdx.json
RUN playwright install chromium --with-deps 2>/dev/null || true

# ──────────────────────────────────────────────────────
# Stage 2: Runtime — minimal image
# ──────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="MAREF Desktop Agent"
LABEL org.opencontainers.image.description="Multi-Agent Recursive Engineering Framework — Desktop Agent"
LABEL org.opencontainers.image.version="0.55.2"
LABEL org.opencontainers.image.licenses="Apache-2.0"

ENV DEBIAN_FRONTEND=noninteractive

# Runtime system dependencies only
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
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

# 基础镜像自带的系统 pip 留在 /usr/local, 运行时实际用 /opt/venv, 但 Trivy 会扫到
# 其元数据并判定多个 CVE (CVE-2025-8869/2026-13346/2026-3219/2026-6357/2026-8643/2026-1703)。
# 显式升级系统 pip 到修复版本 (26.2.0 未在 PyPI 发布, 最新稳定 26.3)。
# pip 26.3 的 bom.cdx.json 声明 pkg:pypi/setuptools@70.3.0, Trivy 会当成已安装包报出
# CVE-2025-47273 (HIGH); 与 /opt/venv 同样删除 SBOM/vendor 清单, 实际未安装该版本。
RUN /usr/local/bin/python3.12 -m pip install --no-cache-dir --upgrade "pip>=26.3" \
    && rm -f /usr/local/lib/python3.12/site-packages/pip/_vendor/vendor.txt \
             /usr/local/lib/python3.12/site-packages/pip/_vendor/bom.cdx.json

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
