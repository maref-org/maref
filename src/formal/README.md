# MAREF TLA+ Formal Specifications

This directory contains TLA+ specifications for the MAREF 10-state
Gray code governance state machine. These specs provide a formal,
machine-checkable model that complements the Python-level verification
in `tests/formal/`.

## Files

| File | Description |
|------|-------------|
| `MarefLite.tla` | Core state machine module — defines states, Gray code encoding, and transition rules |
| `MarefLiteModel.tla` | TLC model configuration — liveness checks, invariants, and temporal properties |
| `MarefLiteMC.cfg` | TLC checker configuration — constants, invariants, and property definitions |
| `MAREF_ConstitutionalRedLines.tla` | **Constitutional red lines (INV-001–005)** — formally verified 5 invariants: agent red line immutability, safety gate integrity, audit trail completeness, constitution supremacy, human constitution sole authority |
| `MAREF_ConstitutionalRedLinesMC.cfg` | TLC checker configuration for the constitutional red lines model |

## Properties Verified

The TLA+ model checks the following properties:

1. **Single Bit Transitions** — Every valid transition changes exactly one Gray code bit
2. **No Self Loops** — No state can transition to itself
3. **Terminal Absorbing** — HALT state has no outgoing edges
4. **Reachability** — All 10 states are reachable from INIT
5. **Entropy Profile** — Entropy follows the mountain curve: 0 → 4 → 0
6. **Gray Code Uniqueness** — All 10 Gray code encodings are distinct

## Properties Verified (Constitutional Red Lines)

The `MAREF_ConstitutionalRedLines` spec checks the 5 constitutional invariants:

| Invariant | TLA+ Name | Description | Status |
|-----------|-----------|-------------|--------|
| INV-001 | `RedLineImmutabilityInv` | Red lines cannot be modified by any agent | ✅ Verified (156 states) |
| INV-002 | `SafetyGateIntegrityInv` | Safety gate is always active | ✅ Verified (156 states) |
| INV-003 | `AuditTrailCompletenessInv` | Every mutation has an audit entry | ✅ Verified (156 states) |
| INV-004 | `ConstitutionSupremacyInv` | Violating decisions are always rejected | ✅ Verified (156 states) |
| INV-005 | `HumanConstitutionSoleAuthorityInv` | Only HumanMaker can create/modify red lines | ✅ Verified (156 states) |

## Running TLC

### Option 1: Docker (Recommended)

> **Note**: First build requires internet (downloads tla2tools.jar from GitHub).
> For offline builds, pre-download the jar and add `COPY tla2tools.jar /usr/local/lib/tla2tools.jar`
> to `Dockerfile.tlc`, removing the `RUN wget` line.

```bash
# Build the TLC Docker image
docker build -t maref-tlc -f Dockerfile.tlc .

# Verify all specifications
docker run --rm maref-tlc

# List available specs
docker run --rm maref-tlc list

# Verify a single spec
docker run --rm maref-tlc MarefLiteModel
docker run --rm maref-tlc MAREF_ConstitutionalRedLines
```

### Option 2: Standalone TLC jar

```bash
# Download tla2tools.jar from https://github.com/tlaplus/tlaplus/releases
java -cp tla2tools.jar tlc2.TLC -config MarefLiteMC.cfg MarefLiteModel

# Constitutional red lines verification
java -cp tla2tools.jar tlc2.TLC -config MAREF_ConstitutionalRedLinesMC.cfg \
  MAREF_ConstitutionalRedLines
```

Expected output (all checks pass):

```
Model checking completed. No error has been found.
  States generated: <N>
  Distinct states: <N>
```

## Relationship to Python Tests

The TLA+ specs are the **source of truth** for the state machine design.
The Python `GrayCodeValidator` in `tests/formal/conftest.py` implements
the same 6 checks as executable tests, ensuring the Python implementation
matches the formal model.

CI runs both:
- `.github/workflows/formal-verify.yml` — Python GrayCodeValidator (fast, runs on every PR)
- TLC model check — TLA+ spec (slower, run on major releases)
