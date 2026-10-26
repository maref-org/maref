"""运行时证言负向测试：过期、篡改、错误公钥、未健康都必须失败。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

REPO_ROOT = Path(__file__).resolve().parents[2]
ATTEST = REPO_ROOT / "scripts" / "runtime_attest.py"
VERIFY = REPO_ROOT / "scripts" / "verify_runtime_attest.py"


def _write_keypair(tmp_path: Path, name: str) -> tuple[Path, Path]:
    private = tmp_path / f"{name}-private.pem"
    public = tmp_path / f"{name}-public.pem"
    if private.is_file() and public.is_file():
        return private, public
    key = Ed25519PrivateKey.generate()
    private.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    public.write_bytes(
        key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return private, public


def _report(healthy: bool = True) -> dict:
    return {
        "timestamp": 1750000000.0,
        "summary": {
            "m0_passed": healthy,
            "m1_passed": True,
            "m2_passed": healthy,
            "m3_passed": True,
            "m4_passed": healthy,
            "all_passed": healthy,
        },
        "m0": {
            "checks": {
                "managed_agents": {
                    "survival_rate": 0.9,
                    "active_total": 30,
                    "dead": [],
                    "retired": [],
                }
            }
        },
        "m1": {"chain_integrity": {"max_records_scanned": 10000, "truncated": False}},
        "m2": {
            "notification_staleness": {"open_alerts": 0, "stale_24h": 0, "stale_72h": 0},
            "alert_channel": {"status": "active"},
        },
        "m4": {"checks": {"guard_block_rate": {"guarded_24h": 3, "coverage": "defined"}}},
        "signature_mode": "ed25519",
    }


def _generate(tmp_path: Path, *, healthy: bool = True, generated_at: str | None = None) -> Path:
    private, _ = _write_keypair(tmp_path, "signer")
    report = tmp_path / "report.json"
    report.write_text(json.dumps(_report(healthy)))
    out = tmp_path / "attest.json"
    cmd = [
        sys.executable,
        str(ATTEST),
        "--report",
        str(report),
        "--private-key",
        str(private),
        "--out",
        str(out),
    ]
    if generated_at:
        cmd += ["--generated-at", generated_at]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return out


def _verify(attest: Path, public: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(VERIFY),
            "--attest",
            str(attest),
            "--public-key",
            str(public),
            "--json",
            *extra,
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_valid_attestation_verifies(tmp_path: Path) -> None:
    attest = _generate(tmp_path)
    _, public = _write_keypair(tmp_path, "signer")  # same files, re-read
    proc = _verify(attest, public)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert json.loads(proc.stdout)["verified"] is True


def test_expired_attestation_fails(tmp_path: Path) -> None:
    old = (datetime.now(timezone.utc) - timedelta(hours=25)).strftime("%Y-%m-%dT%H:%M:%SZ")
    attest = _generate(tmp_path, generated_at=old)
    _, public = _write_keypair(tmp_path, "signer")
    proc = _verify(attest, public)
    assert proc.returncode == 1
    assert any("expired" in p for p in json.loads(proc.stdout)["problems"])


def test_tampered_payload_fails(tmp_path: Path) -> None:
    attest = _generate(tmp_path)
    data = json.loads(attest.read_text())
    data["payload"]["claims"]["all_passed"] = not data["payload"]["claims"]["all_passed"]
    attest.write_text(json.dumps(data))
    _, public = _write_keypair(tmp_path, "signer")
    proc = _verify(attest, public)
    assert proc.returncode == 1
    assert any("signature invalid" in p for p in json.loads(proc.stdout)["problems"])


def test_wrong_public_key_fails(tmp_path: Path) -> None:
    attest = _generate(tmp_path)
    _, other_public = _write_keypair(tmp_path, "intruder")
    proc = _verify(attest, other_public)
    assert proc.returncode == 1
    problems = json.loads(proc.stdout)["problems"]
    assert any("key_id" in p for p in problems)


def test_require_healthy_fails_on_unhealthy_claims(tmp_path: Path) -> None:
    attest = _generate(tmp_path, healthy=False)
    _, public = _write_keypair(tmp_path, "signer")
    assert _verify(attest, public).returncode == 0
    proc = _verify(attest, public, "--require-healthy")
    assert proc.returncode == 1
    assert any("not healthy" in p for p in json.loads(proc.stdout)["problems"])


def test_missing_attestation_is_tooling_error(tmp_path: Path) -> None:
    _, public = _write_keypair(tmp_path, "signer")
    proc = _verify(tmp_path / "missing.json", public)
    assert proc.returncode == 2


def test_missing_signing_key_is_tooling_error(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    report.write_text(json.dumps(_report()))
    env = dict(os.environ)
    env.pop("MAREF_ATTEST_PRIVATE_KEY", None)
    proc = subprocess.run(
        [
            sys.executable,
            str(ATTEST),
            "--report",
            str(report),
            "--out",
            str(tmp_path / "attest.json"),
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert proc.returncode == 2
