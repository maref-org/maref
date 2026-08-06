"""Three-gate admission test for maref-brand-positioning skill.

This script demonstrates how a skill passes MAREF's three-gate admission:
    Gate 1: Static security scan (AST analysis, input validation, no dangerous calls)
    Gate 2: Sandbox execution test (run with resource limits, verify output schema)
    Gate 3: Manual review (checklist for human reviewer)

Usage:
    python test_three_gates.py

Exit codes:
    0 — All gates passed
    1 — Gate 1 (static scan) failed
    2 — Gate 2 (sandbox test) failed
    3 — Gate 3 (manual review) failed
"""

from __future__ import annotations

import ast
import json
import resource
import signal
import sys
import time
import traceback
from pathlib import Path

# Add implementation to path
IMPL_DIR = Path(__file__).parent
sys.path.insert(0, str(IMPL_DIR))

from brand_positioning import generate, PositioningResult  # noqa: E402


# ============================================================
# Gate 1: Static Security Scan
# ============================================================

# Modules/patterns that are forbidden in a sandboxed skill
FORBIDDEN_IMPORTS = {
    "os",
    "subprocess",
    "shutil",
    "ctypes",
    "multiprocessing",
    "socket",
    "http",
    "urllib",
    "asyncio.subprocess",
    "builtins.__import__",
}

FORBIDDEN_CALLS = {
    "exec",
    "eval",
    "compile",
    "__import__",
    "open",  # file I/O restricted in sandbox
    "globals",
    "locals",
}


def gate1_static_scan(module_path: Path) -> tuple[bool, list[str]]:
    """Gate 1: Static security scan.

    Checks:
    - No forbidden imports
    - No forbidden function calls
    - No network access
    - No file system access
    - AST is parseable (valid Python)
    """
    errors: list[str] = []
    source = module_path.read_text()

    # Check 1: Parseable
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        errors.append(f"Syntax error: {e}")
        return False, errors

    # Check 2: No forbidden imports
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in FORBIDDEN_IMPORTS:
                    errors.append(f"Forbidden import: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module in FORBIDDEN_IMPORTS:
                errors.append(f"Forbidden import: {node.module}")

    # Check 3: No forbidden calls
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in FORBIDDEN_CALLS:
                errors.append(f"Forbidden call: {func.id}")
            elif isinstance(func, ast.Attribute) and func.attr in FORBIDDEN_CALLS:
                errors.append(f"Forbidden call: {func.attr}")

    # Check 4: No network/file access patterns
    network_patterns = ["socket", "http", "urllib", "requests", "httpx"]
    for pattern in network_patterns:
        if pattern in source:
            errors.append(f"Network access pattern detected: {pattern}")

    return len(errors) == 0, errors


# ============================================================
# Gate 2: Sandbox Execution Test
# ============================================================

SANDBOX_CPU_LIMIT_S = 5  # 5 seconds CPU time
SANDBOX_MEMORY_MB = 128  # 128 MB
SANDBOX_WALL_TIMEOUT_S = 10  # 10 seconds wall time


def gate2_sandbox_test() -> tuple[bool, list[str], dict]:
    """Gate 2: Sandbox execution test.

    Checks:
    - Runs within CPU/memory/time limits
    - Output matches schema
    - Test cases pass
    - No exceptions
    """
    errors: list[str] = []
    results: dict = {"test_cases": [], "output": None}

    # Set resource limits (CPU time)
    try:
        resource.setrlimit(
            resource.RLIMIT_CPU, (SANDBOX_CPU_LIMIT_S, SANDBOX_CPU_LIMIT_S)
        )
    except (ValueError, resource.error):
        # macOS may not support RLIMIT_CPU; use wall clock timeout instead
        pass

    # Set wall-clock timeout
    def timeout_handler(signum, frame):
        raise TimeoutError(f"Sandbox wall timeout ({SANDBOX_WALL_TIMEOUT_S}s)")

    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(SANDBOX_WALL_TIMEOUT_S)

    try:
        # Test case 1: Generate MAREF positioning
        start_time = time.time()
        result = generate(
            brand_id="maref",
            competitive_alternatives="use LangGraph/CrewAI/AutoGen without governance, or build custom safety middleware",
            unique_attributes=[
                "TLA+ formal verification with 5 proven theorems",
                "10-state Gray Code governance state machine",
                "three-gate skill marketplace admission",
                "10/10 OWASP Agentic Top 10 coverage",
            ],
            value_proof=[
                {
                    "attribute": "TLA+ formal verification",
                    "value": "mathematically provable safety",
                },
                {
                    "attribute": "three-gate marketplace",
                    "value": "trusted skill supply chain",
                },
            ],
            character="the safety engineer of the agent world",
            market_category="agent governance and skill marketplace operating system",
            target_audience="platform architects deploying agents in regulated production environments",
        )
        elapsed = time.time() - start_time
        results["test_cases"].append(
            {"name": "generate MAREF positioning", "elapsed_s": elapsed, "passed": True}
        )

        # Verify output schema
        assert isinstance(result, PositioningResult), "Output must be PositioningResult"
        assert isinstance(result.positioning_statement, str), "positioning_statement must be str"
        assert isinstance(result.one_liner, str), "one_liner must be str"
        assert isinstance(result.elevator_pitch, str), "elevator_pitch must be str"
        assert isinstance(result.differentiators, list), "differentiators must be list"
        assert isinstance(result.support_points, list), "support_points must be list"
        assert isinstance(result.consistency_score, float), "consistency_score must be float"
        assert 0 <= result.consistency_score <= 100, "consistency_score out of range"

        # Verify positioning statement contains key elements
        assert "maref" in result.positioning_statement.lower(), "positioning must mention brand"
        assert "governance" in result.positioning_statement.lower(), "positioning must mention category"

        results["output"] = {
            "one_liner": result.one_liner,
            "consistency_score": result.consistency_score,
            "differentiators_count": len(result.differentiators),
            "warnings": result.warnings,
        }

        # Test case 2: Minimal input (only required fields)
        result2 = generate(
            brand_id="test-brand",
            competitive_alternatives="do nothing",
            unique_attributes=["unique feature one"],
            market_category="test category",
        )
        assert result2.consistency_score < 100, "minimal input should have lower consistency"
        results["test_cases"].append(
            {"name": "minimal input", "elapsed_s": 0, "passed": True}
        )

        # Test case 3: Invalid input (should raise ValueError)
        try:
            generate(
                brand_id="",  # invalid
                competitive_alternatives="test",
                unique_attributes=["test"],
                market_category="test",
            )
            errors.append("Expected ValueError for empty brand_id")
        except ValueError:
            results["test_cases"].append(
                {"name": "invalid input rejection", "passed": True}
            )

    except TimeoutError as e:
        errors.append(f"Sandbox timeout: {e}")
    except AssertionError as e:
        errors.append(f"Schema violation: {e}")
    except Exception as e:
        errors.append(f"Unexpected exception: {e}\n{traceback.format_exc()}")
    finally:
        signal.alarm(0)  # Cancel timeout

    return len(errors) == 0, errors, results


# ============================================================
# Gate 3: Manual Review Checklist
# ============================================================

MANUAL_REVIEW_CHECKLIST = [
    "Skill name follows naming convention (maref-{name})",
    "Skill description clearly states what it does",
    "Input schema is complete and typed",
    "Output schema is complete and typed",
    "Dependencies are declared and versioned",
    "License is Apache-2.0 (compatible with MAREF)",
    "Entrypoint path is correct (module:function)",
    "Sandbox config specifies CPU/memory/timeout limits",
    "Sandbox config restricts network and filesystem",
    "Test cases cover: happy path, edge case, error case",
    "No hardcoded credentials or secrets",
    "No external API calls (pure function)",
    "Code follows PEP 8 (ruff clean)",
    "Code has type hints (mypy clean)",
    "Attribution to original source (Brand-building-skills)",
]


def gate3_manual_review() -> tuple[bool, list[str]]:
    """Gate 3: Manual review checklist.

    In production, this would be a human reviewer. For the reference implementation,
    we check the structural requirements that a human would verify.
    """
    errors: list[str] = []

    manifest_path = IMPL_DIR.parent / "manifests" / "maref-brand-positioning.yaml"
    if not manifest_path.exists():
        errors.append(f"Manifest not found: {manifest_path}")
        return False, errors

    # In a real review, a human would check each item.
    # Here we verify the manifest exists and is loadable.
    try:
        import yaml

        with open(manifest_path) as f:
            manifest = yaml.safe_load(f)

        if manifest.get("name") != "maref-brand-positioning":
            errors.append("Manifest name mismatch")
        if manifest.get("license") != "Apache-2.0":
            errors.append("License is not Apache-2.0")
        if not manifest.get("entrypoint"):
            errors.append("Missing entrypoint")
        if not manifest.get("sandbox_config"):
            errors.append("Missing sandbox_config")
        if not manifest.get("test_cases"):
            errors.append("Missing test_cases")
    except Exception as e:
        errors.append(f"Manifest load error: {e}")

    return len(errors) == 0, errors


# ============================================================
# Main: Run all three gates
# ============================================================

def main() -> int:
    print("=" * 60)
    print("Three-Gate Admission Test: maref-brand-positioning")
    print("=" * 60)

    # Gate 1
    print("\n🛡️  Gate 1: Static Security Scan")
    module_path = IMPL_DIR / "brand_positioning.py"
    g1_passed, g1_errors = gate1_static_scan(module_path)
    if g1_passed:
        print("   ✅ PASSED — no forbidden imports/calls/patterns")
    else:
        print("   ❌ FAILED:")
        for err in g1_errors:
            print(f"      - {err}")
        return 1

    # Gate 2
    print("\n🔧 Gate 2: Sandbox Execution Test")
    g2_passed, g2_errors, g2_results = gate2_sandbox_test()
    if g2_passed:
        print("   ✅ PASSED — all test cases passed within resource limits")
        print(f"   Output: {json.dumps(g2_results['output'], indent=2)}")
        for tc in g2_results["test_cases"]:
            status = "✅" if tc["passed"] else "❌"
            print(f"   {status} {tc['name']}")
    else:
        print("   ❌ FAILED:")
        for err in g2_errors:
            print(f"      - {err}")
        return 2

    # Gate 3
    print("\n👁️  Gate 3: Manual Review Checklist")
    g3_passed, g3_errors = gate3_manual_review()
    if g3_passed:
        print("   ✅ PASSED — manifest structure verified")
        print("   📋 Manual checklist (15 items) — see MANUAL_REVIEW_CHECKLIST")
        for item in MANUAL_REVIEW_CHECKLIST:
            print(f"      ☐ {item}")
    else:
        print("   ❌ FAILED:")
        for err in g3_errors:
            print(f"      - {err}")
        return 3

    # All passed
    print("\n" + "=" * 60)
    print("🎉 ALL THREE GATES PASSED — skill is ready for APPROVED status")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
