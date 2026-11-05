#!/usr/bin/env python3
"""审计链外部锚定：批次 Merkle 根 + RFC 3161 时间戳。

哈希链能发现就地篡改，却无法证明"历史没有被整段删除后重写"。
本脚本用 :class:`AuditAnchor` 把审计 JSONL 切成批次、计算 Merkle
根，并为每批向公开 TSA 申请 RFC 3161 时间戳。输出目录包含锚点、
请求、令牌与 TSA 根证书，可随 GitHub Release 公开。

与 ``AuditAnchor`` 运行时的 fail-open 语义不同，本脚本 fail-closed：
任一锚点缺少有效时间戳即非零退出，因为这是发布前置检查，不是
可选增强。

第三方验证（无需信任本仓库）::

    python3 scripts/verify_audit_anchor.py \\
        --audit <audit.jsonl> --anchors <out-dir>/anchors.jsonl
    openssl ts -verify -in <out-dir>/batches/<root>.tsr \\
        -queryfile <out-dir>/batches/<root>.tsq \\
        -CAfile <out-dir>/freetsa-cacert.pem
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = _REPO_ROOT / "src"
for _path in (_SRC, _REPO_ROOT / "scripts"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import rfc3161_stamp as stamp  # noqa: E402

from maref.governance.audit_anchor import AuditAnchor, verify_anchors  # noqa: E402


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _trim_incomplete_anchors(anchors_path: Path) -> int:
    """截断第一个无令牌锚点及其后记录，使失败批次可在重跑时重做。

    AuditAnchor 运行时是 fail-open：TSA 失败仍会追加锚点（token 为空）。
    发布脚本要求 fail-closed，因此把这段"已写但无时间证明"的尾巴
    丢掉，否则后续运行会把它当作已锚定而永久跳过。
    """
    if not anchors_path.exists():
        return 0
    lines = [line for line in anchors_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    keep: list[str] = []
    for line in lines:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            break
        if not record.get("tsa_token"):
            break
        keep.append(line)
    removed = len(lines) - len(keep)
    if removed:
        anchors_path.write_text("\n".join(keep) + ("\n" if keep else ""), encoding="utf-8")
    return removed


def _stamp_root(root: str, batches_dir: Path, args, ca_path: Path) -> str:
    """为单个 Merkle 根申请并验证时间戳，返回 base64 令牌。"""
    batches_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp) / "root.bin"
        data.write_bytes(bytes.fromhex(root))
        tsq_path = Path(tmp) / "request.tsq"
        tsr_path = Path(tmp) / "response.tsr"
        stamp.create_query(data, tsq_path)
        stamp.request_token(tsq_path, tsr_path, args.tsa_url, args.timeout)
        stamp.verify_token(tsq_path, tsr_path, ca_path)
        # 临时目录可能在另一文件系统（如 TMPDIR 在内置盘、锚点目录在外置
        # 盘），os.replace 会抛 EXDEV；shutil.move 跨设备时退化为复制。
        shutil.move(str(tsq_path), str(batches_dir / f"{root[:16]}.tsq"))
        shutil.move(str(tsr_path), str(batches_dir / f"{root[:16]}.tsr"))
        return base64.b64encode((batches_dir / f"{root[:16]}.tsr").read_bytes()).decode("ascii")


def _verify_all_tokens(anchors, batches_dir: Path, ca_path: Path) -> list[str]:
    """离线重验每个锚点的令牌与 Merkle 根，返回问题列表。

    必须复用落盘的原始 ``.tsq``（含签发时的 nonce）；重新生成请求会
    产生新 nonce，导致 ``nonce mismatch`` 的假阴性。
    """
    problems: list[str] = []
    for anchor in anchors:
        if not anchor.tsa_token:
            problems.append(f"batch {anchor.batch_start_id} has no timestamp token")
            continue
        if len(anchor.merkle_root) != 64:
            problems.append(f"batch {anchor.batch_start_id} has invalid merkle root")
            continue
        prefix = anchor.merkle_root[:16]
        tsq_path = batches_dir / f"{prefix}.tsq"
        tsr_path = batches_dir / f"{prefix}.tsr"
        if not tsq_path.exists() or not tsr_path.exists():
            problems.append(f"batch {anchor.batch_start_id}: missing request/token file")
            continue
        if base64.b64encode(tsr_path.read_bytes()).decode("ascii") != anchor.tsa_token:
            problems.append(f"batch {anchor.batch_start_id}: token file does not match anchor")
            continue
        try:
            stamp.verify_token(tsq_path, tsr_path, ca_path)
        except stamp.TimestampError as exc:
            problems.append(f"batch {anchor.batch_start_id}: {exc}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Anchor audit batches with RFC 3161 timestamps")
    parser.add_argument(
        "--audit",
        default=str(_REPO_ROOT / ".governance" / "governance_audit.jsonl"),
        help="audit JSONL path",
    )
    parser.add_argument("--out-dir", required=True, help="output directory for anchors and tokens")
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--tsa-url", default=stamp.FREE_TSA_URL)
    parser.add_argument("--ca-url", default=stamp.FREE_TSA_CA_URL)
    parser.add_argument("--ca-sha256", default=stamp.FREE_TSA_CA_SHA256)
    parser.add_argument("--timeout", type=float, default=stamp.DEFAULT_TIMEOUT)
    args = parser.parse_args(argv)
    if args.batch_size < 1:
        parser.error("--batch-size must be >= 1")

    audit_path = Path(args.audit)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    anchors_path = out_dir / "anchors.jsonl"
    batches_dir = out_dir / "batches"
    ca_path = out_dir / "freetsa-cacert.pem"

    try:
        stamp.fetch_ca(args.ca_url, args.ca_sha256, ca_path, args.timeout)

        def tsa(root: str) -> str:
            return _stamp_root(root, batches_dir, args, ca_path)

        trimmed = _trim_incomplete_anchors(anchors_path)
        if trimmed:
            print(f"trimmed {trimmed} anchor record(s) without timestamp tokens")
        anchor = AuditAnchor(
            audit_path=audit_path,
            anchors_path=anchors_path,
            batch_size=args.batch_size,
            tsa=tsa,
        )
        created = anchor.anchor_now()
        anchors = anchor.anchors()

        anchor_report = verify_anchors(audit_path, anchors_path)
        token_problems = _verify_all_tokens(anchors, batches_dir, ca_path)
    except (stamp.TimestampError, ValueError) as exc:
        print(f"audit anchor FAILED: {exc}", file=sys.stderr)
        return 1

    issues = list(anchor_report.issues) + token_problems
    if issues:
        print("audit anchor FAILED:", file=sys.stderr)
        for issue in issues:
            print(f"  - {issue}", file=sys.stderr)
        return 1

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "audit_file": str(audit_path),
        "audit_sha256": _sha256_file(audit_path),
        "anchors_sha256": _sha256_file(anchors_path),
        "tsa_url": args.tsa_url,
        "tsa_ca_sha256": args.ca_sha256,
        "batch_size": args.batch_size,
        "total_events": anchor_report.total_events,
        "anchored_events": anchor_report.anchored_events,
        "uncovered_events": anchor_report.uncovered_events,
        "batches": [
            {
                **record.to_dict(),
                "token_file": f"batches/{record.merkle_root[:16]}.tsr",
                "request_file": f"batches/{record.merkle_root[:16]}.tsq",
            }
            for record in anchors
        ],
    }
    (out_dir / "ANCHOR_MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(
        f"audit anchor OK: {len(created)} new batches, {len(anchors)} total, "
        f"{anchor_report.anchored_events}/{anchor_report.total_events} events anchored, "
        f"{anchor_report.uncovered_events} uncovered"
    )
    print(f"  anchors: {anchors_path}")
    print(f"  manifest: {out_dir / 'ANCHOR_MANIFEST.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
