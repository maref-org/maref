#!/usr/bin/env python3
"""离线复核审计锚点产物（ANCHOR_MANIFEST.json + anchors + 令牌）。

锚点由 :mod:`anchor_governance_audit` 在审计链所在机器上生成，产物不含
审计原文，可安全交给第三方复核。本脚本只做离线校验，不访问 TSA，也不
需要审计 JSONL：

- ``anchors.jsonl`` 的 SHA-256 与 manifest 记录一致；
- TSA 根证书指纹与 manifest 记录一致（防替换 CA）；
- 每个批次证书文件的 Base64 与锚点内 ``tsa_token`` 一致；
- 逐批 ``openssl ts -verify`` 校验时间戳令牌。

它证明的是"该 Merkle 根在令牌声明的时间点已存在"，而不是"根对应某段
审计原文"——后者需要审计原文，只能在数据侧用 ``verify_audit_anchor.py``。

用法::

    python3 scripts/verify_anchor_manifest.py --dir <anchor-out-dir>
    python3 scripts/verify_anchor_manifest.py --dir <dir> --audit audit.jsonl
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

MANIFEST_NAME = "ANCHOR_MANIFEST.json"
ANCHORS_NAME = "anchors.jsonl"
CA_NAME = "freetsa-cacert.pem"
DEFAULT_OPENSSL = shutil.which("openssl")


class ManifestError(RuntimeError):
    """锚点产物缺失、损坏或与 manifest 不一致。"""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_manifest(root: Path) -> dict:
    path = root / MANIFEST_NAME
    if not path.exists():
        raise ManifestError(f"manifest not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ManifestError(f"manifest is not valid JSON: {exc}") from exc


def _load_anchors(root: Path) -> list[dict]:
    path = root / ANCHORS_NAME
    if not path.exists():
        raise ManifestError(f"anchors not found: {path}")
    records: list[dict] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ManifestError(f"anchors line {lineno} is not JSON: {exc}") from exc
    return records


def _check_digest(label: str, path: Path, expected: str, problems: list[str]) -> None:
    if not path.exists():
        problems.append(f"{label} missing: {path.name}")
        return
    actual = sha256_file(path)
    if actual != expected:
        problems.append(f"{label} sha256 mismatch: {actual} != {expected}")


def _verify_token(
    tsr: Path, tsq: Path, ca: Path, openssl: str, label: str, problems: list[str]
) -> None:
    for path in (tsr, tsq):
        if not path.exists():
            problems.append(f"{label}: missing {path.name}")
            return
    result = subprocess.run(
        [openssl, "ts", "-verify", "-in", str(tsr), "-queryfile", str(tsq), "-CAfile", str(ca)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or "Verification: OK" not in result.stdout:
        detail = (result.stderr or result.stdout).strip().splitlines()
        tail = detail[-1] if detail else "unknown openssl error"
        problems.append(f"{label}: timestamp verification failed: {tail}")


def _check_batch(
    root: Path, batch: dict, anchor: dict, ca: Path, openssl: str, problems: list[str]
) -> None:
    root_hex = str(anchor.get("merkle_root", ""))
    label = f"batch {anchor.get('batch_start_id', '?')}"
    if not root_hex or len(root_hex) != 64:
        problems.append(f"{label}: invalid merkle_root")
        return
    for key in ("batch_start_id", "batch_end_id", "merkle_root", "event_count", "tsa_token"):
        if batch.get(key) != anchor.get(key):
            problems.append(f"{label}: anchors/manifest mismatch on {key}")
            return
    token = str(anchor.get("tsa_token", ""))
    if not token:
        problems.append(f"{label}: anchor has no timestamp token")
        return
    tsr = root / str(batch.get("token_file", ""))
    tsq = root / str(batch.get("request_file", ""))
    if not tsr.exists() or not tsq.exists():
        problems.append(f"{label}: missing request/token file")
        return
    if base64.b64encode(tsr.read_bytes()).decode("ascii") != token:
        problems.append(f"{label}: token file does not match anchor")
        return
    _verify_token(tsr, tsq, ca, openssl, label, problems)


def verify(root: Path, audit: Path | None = None, openssl: str | None = None) -> list[str]:
    problems: list[str] = []
    manifest = _load_manifest(root)
    anchors = _load_anchors(root)

    _check_digest(
        "anchors.jsonl", root / ANCHORS_NAME, str(manifest.get("anchors_sha256", "")), problems
    )
    _check_digest(
        "freetsa-cacert.pem", root / CA_NAME, str(manifest.get("tsa_ca_sha256", "")), problems
    )
    if audit is not None:
        _check_digest("audit.jsonl", audit, str(manifest.get("audit_sha256", "")), problems)

    batches = manifest.get("batches") or []
    if len(batches) != len(anchors):
        problems.append(f"batch count mismatch: manifest={len(batches)} anchors={len(anchors)}")

    binary = openssl or DEFAULT_OPENSSL
    if binary is None:
        problems.append("openssl not found")
        return problems

    ca = root / CA_NAME
    for batch, anchor in zip(batches, anchors, strict=False):
        _check_batch(root, batch, anchor, ca, binary, problems)
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify anchored audit artifacts offline")
    parser.add_argument("--dir", required=True, help="directory holding anchor artifacts")
    parser.add_argument("--audit", help="optional audit JSONL to check audit_sha256")
    parser.add_argument("--openssl", default=DEFAULT_OPENSSL, help="openssl binary")
    args = parser.parse_args(argv)

    root = Path(args.dir)
    audit = Path(args.audit) if args.audit else None
    try:
        problems = verify(root, audit=audit, openssl=args.openssl)
    except ManifestError as exc:
        print(f"anchor manifest FAILED: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"anchor manifest FAILED: {exc}", file=sys.stderr)
        return 1

    if problems:
        print("anchor manifest FAILED:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    manifest = _load_manifest(root)
    print(
        "anchor manifest OK: "
        f"{manifest.get('anchored_events')}/{manifest.get('total_events')} events, "
        f"{len(manifest.get('batches') or [])} batches"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
