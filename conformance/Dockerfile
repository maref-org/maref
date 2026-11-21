# Stdlib-only runner: the conformance suite must not require MAREF's dependencies.
FROM python:3.12-slim

WORKDIR /suite

COPY src/maref/conformance ./src/maref/conformance
COPY src/maref/__init__.py ./src/maref/__init__.py
COPY scripts/conformance_run.py ./scripts/conformance_run.py
COPY conformance ./conformance

ENTRYPOINT ["python", "scripts/conformance_run.py"]
