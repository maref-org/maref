# Code Smell Remediation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix critical and high-severity issues identified in the code audit — restore test infrastructure, fix type safety, clean up garbage, and establish engineering hygiene.

**Root Cause (P0):** Global `site-packages` has `_editable_impl_maref.pth` injecting `上游开发仓库的 src` into PYTHONPATH. All `import maref.*` resolves to the `openclaw` copy (missing `budget.py`, `topology.py`, `vector_store.py`, `consolidation_gate.py`), causing 32 test collection failures and 0% coverage.

**Tech Stack:** Python 3.10+ / mypy / ruff / pytest / hatchling

---

## Task 1: Kill PYTHONPATH Pollution — Fix Editable Install

**Files:**
- Check: `/opt/homebrew/lib/python3.14/site-packages/_editable_impl_maref.pth`
- Check: `/opt/homebrew/lib/python3.14/site-packages/_editable_impl_percv.pth`
- Create: `scripts/fix-pythonpath.sh`
- Create: `.envrc` (direnv) or update `.venv/bin/activate`

**Context:** The `.pth` file injects `上游开发仓库 src` globally into *every* Python 3.14 invocation. This repo needs `maref` to resolve to `public/maref/src/maref`, not `上游开发仓库 src/maref`.

**Step 1: Diagnose the .pth files**

```bash
cat /opt/homebrew/lib/python3.14/site-packages/_editable_impl_maref.pth
```

Expected: shows the openclaw src path.

**Step 2: Verify pip's editable install target**

```bash
pip show maref  # Shows Location and Editable project location
```

**Step 3: Uninstall the global editable install**

```bash
pip uninstall maref -y
```

**Step 4: Install the correct version from this repo**

```bash
pip install -e "src/" --no-build-isolation
# or if the above fails:
PYTHONPATH=src pip install -e ".[dev]" --no-build-isolation
```

**Step 5: Verify the fix**

```bash
python3 -c "import maref.executor.budget; print('OK')"
```

Expected: no ImportError.

**Step 6: Verify tests can collect**

```bash
pytest tests/executor/test_budget.py --collect-only -q
```

Expected: collected 1 item.

**Step 7: Create a fix script for future**

Create `scripts/fix-pythonpath.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail
echo "[fix-pythonpath] Uninstalling global maref editable install..."
pip uninstall maref -y 2>/dev/null || true
echo "[fix-pythonpath] Installing maref from current repo..."
pip install -e ".[dev]" --no-build-isolation
echo "[fix-pythonpath] Verifying..."
python3 -c "from maref.executor.budget import BudgetTracker; print('OK')"
```

**Step 8: Commit**

```bash
git add scripts/fix-pythonpath.sh
git commit -m "fix: add script to repair PYTHONPATH pollution from 上游开发仓库的 editable install"
```

---

## Task 2: Run `ruff --fix` — Auto-Repair 30 Lint Errors

**Files:**
- Modify: `src/maref/__main__.py`, `src/maref/crypto/aia_adapter.py`, `src/maref/crypto/benchmark.py`, `src/maref/crypto/sm4.py`, `src/maref/executor/governance_aware_scheduler.py`, `src/maref/executor/warm_pool.py`, `src/maref/governance/threat_bridge.py`, `src/maref/governance/trust_bridge.py`, `src/maref/human/decision_api.py`, `src/maref/human/rule_engine.py`, `src/maref/marketplace/__init__.py`, `src/maref/memory/consolidation_gate.py`, `src/maref/memory/memory_manager.py`, `src/maref/observation/topology.py`, `src/maref/orchestration/dispatcher.py`, `src/maref/orchestration/joint_machine.py`, `src/maref/recursive/blast_radius.py`, `src/maref/recursive/saga_orchestrator.py`, `src/maref/security/sanitizer.py`, `src/maref/stress/emergence_harness.py`, `src/maref_lite/cli.py`, `src/maref_lite/governance.py`, `src/maref_lite/recursive_governance.py`, `src/research/autoresearch_loop.py`, `src/sidecar/obs_bridge.py`

**Step 1: Run automated fix**

```bash
ruff check src/ --fix
```

**Step 2: Verify remaining errors**

```bash
ruff check src/
```

Should show 5 errors remaining (mostly manual-fix only like `UP035`/`SIM110`).

**Step 3: Verify tests still pass**

```bash
pytest tests/ -q --no-header 2>&1 | tail -5
```

**Step 4: Commit**

```bash
git add src/ 
git commit -m "style: auto-fix 30 ruff lint issues (unused imports, sort order, etc.)"
```

---

## Task 3: Fix mypy Crypto Module Exports (11 Errors)

**Files:**
- Modify: `src/maref/crypto/sm2.py`
- Modify: `src/maref/crypto/sm3.py`
- Modify: `src/maref/crypto/sm4_gcm.py`
- Test: run `mypy src/maref/crypto/`

**Step 1: Check what `sm2.py` exports**

```bash
grep -n "^def \|^class " src/maref/crypto/sm2.py
```

**Step 2: Check what `benchmark.py` imports from sm2**

```bash
grep "from .sm2 import" src/maref/crypto/benchmark.py
```

**Step 3: Add missing exports to `sm2.py`**

```python
# Add at end of sm2.py, or ensure these are defined:
def sm2_encrypt(public_key: bytes, data: bytes) -> bytes: ...
def sm2_decrypt(private_key: bytes, ciphertext: bytes) -> bytes: ...
def sm2_sign(private_key: bytes, data: bytes, *, public_key: bytes | None = None, use_sm3: bool = True) -> bytes: ...
def sm2_verify(public_key: bytes, data: bytes, signature: bytes, *, use_sm3: bool = True) -> bool: ...
```

If these are implemented elsewhere (e.g., in `aia_adapter.py` or `gmssl`-based), expose them via `__init__.py` or add proper stubs.

**Step 4: Add missing exports to `sm3.py`**

```python
def sm3_hash(data: bytes) -> bytes: ...
def sm3_hmac(key: bytes, data: bytes) -> bytes: ...
```

**Step 5: Add missing exports to `sm4_gcm.py`**

```python
def sm4_encrypt_gcm(...): ...
def sm4_decrypt_gcm(...): ...
```

**Step 6: Verify**

```bash
mypy src/maref/crypto/ --ignore-missing-imports
```

Expect: 0 errors in crypto module.

**Step 7: Commit**

```bash
git add src/maref/crypto/
git commit -m "fix(crypto): export missing sm2/sm3/sm4_gcm functions for mypy"
```

---

## Task 4: Fix mypy vector_clock CausalRelation Return Type

**Files:**
- Modify: `src/maref/consensus/vector_clock.py`

**Step 1: Read current code**

```bash
head -80 src/maref/consensus/vector_clock.py
```

**Step 2: Identify the enum/class for CausalRelation**

The file returns raw strings `"concurrent"`, `"before"`, `"after"`, `"equal"` from `compare()`.

**Step 3: Fix: use Literal or the enum**

If `CausalRelation` is a `Literal` type alias:
```python
CausalRelation = Literal["concurrent", "before", "after", "equal"]
```
Or if a `StrEnum`, use the enum members:
```python
class CausalRelation(str, Enum):
    CONCURRENT = "concurrent"
    BEFORE = "before"
    AFTER = "after"
    EQUAL = "equal"
```

**Step 4: Verify**

```bash
mypy src/maref/consensus/vector_clock.py
```

**Step 5: Commit**

```bash
git add src/maref/consensus/vector_clock.py
git commit -m "fix: correct CausalRelation return type in vector_clock"
```

---

## Task 5: Fix mypy GovernanceAwareScheduler Missing Attributes

**Files:**
- Modify: `src/maref/executor/governance_aware_scheduler.py`
- Read: `src/maref/executor/scheduler.py` (the parent class)

**Step 1: Check if `halted` and `faulty_agents` exist on parent**

```bash
grep -n "halted\|faulty_agents" src/maref/executor/scheduler.py
```

**Step 2: Either add them to the parent class, or define them locally:**

If they should exist:
```python
class Scheduler:
    halted: bool = False
    faulty_agents: set[str] = field(default_factory=set)
```

If they're computed properties, add `@property` or class var.

**Step 3: Verify**

```bash
mypy src/maref/executor/governance_aware_scheduler.py
```

**Step 4: Commit**

```bash
git add src/maref/executor/
git commit -m "fix: add halted/faulty_agents attributes to Scheduler base class"
```

---

## Task 6: Fix mypy Remaining Scattered Errors

**Files:** Multiple (see audit report)

**Step 1: Fix observation/topology.py type mismatch**

File `src/maref/observation/topology.py:158-159` — `str` assigned to `tuple[str, str]`. Fix the variable annotation or the assignment.

**Step 2: Fix plan_executor.py list subtraction**

File `src/maref/orchestration/plan_executor.py:206` — `-` operator on `list[str]`. Use set difference or list comprehension.

**Step 3: Fix plan_executor.py None checks**

```python
# Before:
node.status
# After:
if node is not None:
    node.status
```

**Step 4: Fix governance/db.py Row indexing**

```python
# Before:
row["column"]
# After:
if row is not None:
    row["column"]
```

**Step 5: Fix governance_router.py TenantManager**

Add `get_by_id` method or fix the call.

**Step 6: Verify**

```bash
mypy src/ --ignore-missing-imports
```

Expect: significantly fewer than 56 errors (target: <20 remaining, mostly research/ dir).

**Step 7: Commit**

```bash
git add src/maref/
git commit -m "fix: resolve scattered mypy type errors across 6 modules"
```

---

## Task 7: Stop Tracking Garbage in Git

**Files:**
- Modify: `.gitignore` (if needed)
- Run: `git rm --cached` on tracked garbage

**Step 1: Remove garbage from git tracking**

```bash
git rm --cached coverage.json governance_observations.db
```

**Step 2: Verify gitignore catches them**

```bash
echo "coverage.json" >> .gitignore    # already listed, but ensure it's effective
git status
```

**Step 3: Add missing ignores if any**

Check `.gitignore` for anything missing:
- `governance_audit_*.jsonl` — already listed
- `policy_versions/` already listed
- `coverage_per_module_report.json` — add if not present

**Step 4: Commit**

```bash
git commit -m "chore: stop tracking coverage.json and governance_observations.db"
```

---

## Task 8: Clean Up Working Tree Garbage

**Files:**
- Delete: `coverage.json`, `governance_audit.jsonl`, `governance_audit_20260518_113148.jsonl`, `bandit_report.json`, `governance_observations.db`
- Delete: `policy_versions/` directory contents

**Step 1: Remove runtime garbage from working tree**

```bash
# Confirm gitignore covers these, then:
rm -f coverage.json governance_audit.jsonl governance_audit_20260518_113148.jsonl bandit_report.json governance_observations.db
rm -rf policy_versions/
```

**Step 2: Verify tree is clean**

```bash
git status
```

Should show no untracked garbage.

**Step 3: Commit**

```bash
git add -A
git commit -m "chore: remove runtime-generated garbage files (~410MB)"
```

---

## Task 9: Re-run Full Test Suite and Validate Coverage

**Step 1: Run full test collection**

```bash
pytest tests/ --collect-only -q 2>&1 | tail -5
```

Expected: "collected N items, no errors" (0 errors).

**Step 2: Run full test suite**

```bash
pytest tests/ --tb=short -q 2>&1 | tail -20
```

Note the pass/fail rate.

**Step 3: Run with coverage**

```bash
pytest tests/ -v --cov=src --cov-report=term-missing --cov-report=json
```

**Step 4: Check coverage against fail_under**

```bash
python3 -c "import json; d=json.load(open('coverage.json')); print(f'Overall: {d[\"totals\"][\"percent_covered\"]:.1f}%')"
```

Should meet the `fail_under = 70` threshold.

---

## Task 10: Fix Large `__init__.py` Files

**Files:**
- Modify: `src/maref/recursive/__init__.py` (716 lines — largest)
- Modify: `src/maref/compliance/pci_dss/__init__.py` (436 lines)
- Modify: `src/maref/compliance/hipaa/__init__.py` (453 lines)
- Modify: `src/maref/security/trust_integration/__init__.py` (392 lines)
- Modify: `src/maref/security/agent_identity/__init__.py` (349 lines)

**Context:** Large `__init__.py` files defeat lazy loading, increase import time, and often indicate missing module decomposition.

**Step 1: Analyze recursive/__init__.py**

```bash
# Count what's in it
grep -c "^from \|^import " src/maref/recursive/__init__.py
grep -c "^class \|^def " src/maref/recursive/__init__.py
```

**Step 2: Split into sub-modules** (one task per file)

For each large `__init__.py`:
1. Extract class definitions into separate `.py` files
2. Keep only re-exports in `__init__.py` 
3. Use lazy imports where possible

Example pattern:
```python
# __init__.py — just re-exports
from maref.recursive.trust_engine import TrustEngine
from maref.recursive.evolution_dsl import EvolutionDSL
# ... etc
```

**Step 3: Verify imports still work**

```bash
python3 -c "import maref.recursive; print('OK')"
pytest tests/recursive/ -q --no-header 2>&1 | tail -5
```

**Step 4: Commit per file**

```bash
git add src/maref/recursive/
git commit -m "refactor: split 716-line recursive/__init__.py into sub-modules"
```

---

## Task 11: Eliminate Bare `except Exception:` Blocks

**Files:**
- `src/research/autoresearch_loop.py` (8 occurrences)
- `src/research/autoresearch_phase10.py` (4 occurrences)
- `src/research/autoresearch_phase9.py` (4 occurrences)
- `src/maref/crypto/aia_adapter.py` (1)
- `src/maref/tools/web_search_server.py` (3)

**Step 1: Fix each bare except**

Pattern:
```python
# Before:
except Exception:
    pass  # or nothing

# After:
except Exception as e:
    logger.warning("operation failed", error=str(e))
    # Or at minimum:
    raise
```

**Step 2: Commit**

```bash
git add src/research/ src/maref/crypto/aia_adapter.py src/maref/tools/
git commit -m "fix: replace bare except Exception with proper logging/error handling"
```

---

## Task 12: Clean Up `.venv` Proliferation & Standardize Python Version

**Files:**
- Modify: `.venv/bin/activate` (or just document)
- Maybe delete: `.venv2/`, `.venv3/`
- Create: `Makefile` with `make venv` target (optional)

**Step 1: Check pyproject.toml Python version compatibility**

Already `requires-python = ">=3.10"`. The `.venv3` (3.11) is the only safe version.

**Step 2: Remove stale virtual environments**

```bash
rm -rf .venv .venv2  # keep only .venv3
mv .venv3 .venv       # rename to standard
```

**Step 3: Update .gitignore to block future proliferation**

```gitignore
.venv2/
.venv3/
```

**Step 4: Document in AGENTS.md**

Add: `Python 3.11 recommended. Use .venv/.`

**Step 5: Commit**

```bash
git add AGENTS.md .gitignore
git commit -m "chore: consolidate to single .venv (Python 3.11)"
```
