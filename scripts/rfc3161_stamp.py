#!/usr/bin/env python3
"""RFC 3161 时间戳：为发布产物生成可被第三方独立验证的时间证明。

哈希只能证明"内容未变"，不能证明"何时存在"。本脚本对产物清单
（SHA256SUMS）向公开 TSA 申请 RFC 3161 时间戳令牌，并把令牌与
TSA 根证书一起放入产物目录：

- ``SHA256SUMS``：每个发布产物的 SHA-256，兼容 ``sha256sum -c``；
- ``SHA256SUMS.tsq``：时间戳请求（DER）；
- ``SHA256SUMS.tsr``：TSA 签发的时间戳令牌（DER）；
- ``freetsa-cacert.pem``：验证令牌所需的根证书。

CA 指纹在脚本内固定，下载后必须匹配，避免"根证书与令牌同时被
替换"的中间人伪造。任何一步失败都以非零退出（fail-closed），
因为外部锚是发布的前置条件，而不是可选增强。

第三方验证（无需信任本仓库）：

    openssl ts -verify -in SHA256SUMS.tsr -queryfile SHA256SUMS.tsq \\
        -CAfile freetsa-cacert.pem
    sha256sum -c SHA256SUMS
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

FREE_TSA_URL = "https://freetsa.org/tsr"
FREE_TSA_CA_URL = "https://freetsa.org/files/cacert.pem"
FREE_TSA_CA_SHA256 = "2151b61137ffa86bf664691ba67e7da0b19f98c758e3d228d5d8ebf27e044438"

MANIFEST_NAME = "SHA256SUMS"
GENERATED_NAMES = {
    MANIFEST_NAME,
    f"{MANIFEST_NAME}.tsq",
    f"{MANIFEST_NAME}.tsr",
    "freetsa-cacert.pem",
}
DEFAULT_TIMEOUT = 30.0


class TimestampError(RuntimeError):
    """时间戳链路任一环节失败（fail-closed）。"""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect_artifacts(files: list[Path], out_dir: Path) -> list[Path]:
    """过滤掉脚本自己生成的文件，避免重跑时清单包含旧清单。"""
    selected: list[Path] = []
    for path in files:
        if not path.is_file():
            raise TimestampError(f"artifact not found: {path}")
        if path.parent.resolve() == out_dir.resolve() and path.name in GENERATED_NAMES:
            continue
        selected.append(path)
    if not selected:
        raise TimestampError("no artifacts to stamp")
    return selected


def write_manifest(files: list[Path], out_dir: Path) -> Path:
    """生成 sha256sum 兼容清单，按文件名排序保证可复现。"""
    manifest = out_dir / MANIFEST_NAME
    lines = [f"{sha256_file(path)}  {path.name}" for path in sorted(files)]
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return manifest


def _openssl(*args: str) -> subprocess.CompletedProcess[str]:
    binary = shutil.which("openssl")
    if binary is None:
        raise TimestampError("openssl not found on PATH; RFC 3161 requires OpenSSL 3.x")
    return subprocess.run(
        [binary, *args],
        capture_output=True,
        text=True,
        check=False,
    )


def fetch_ca(url: str, expected_sha256: str, out_path: Path, timeout: float) -> Path:
    """下载 TSA 根证书并校验固定指纹；不匹配即拒绝。"""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            payload = resp.read()
    except OSError as exc:
        raise TimestampError(f"failed to download TSA CA from {url}: {exc}") from exc
    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected_sha256:
        raise TimestampError(
            f"TSA CA fingerprint mismatch: expected {expected_sha256}, got {actual}"
        )
    out_path.write_bytes(payload)
    return out_path


def create_query(manifest: Path, tsq_path: Path) -> None:
    result = _openssl(
        "ts", "-query", "-data", str(manifest), "-sha256", "-cert", "-out", str(tsq_path)
    )
    if result.returncode != 0:
        raise TimestampError(f"openssl ts -query failed: {result.stderr.strip()}")


def request_token(tsq_path: Path, tsr_path: Path, tsa_url: str, timeout: float) -> None:
    payload = tsq_path.read_bytes()
    request = urllib.request.Request(
        tsa_url,
        data=payload,
        headers={
            "Content-Type": "application/timestamp-query",
            "User-Agent": "maref-rfc3161-stamp",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            content_type = resp.headers.get("Content-Type", "")
            token = resp.read()
    except OSError as exc:
        raise TimestampError(f"TSA request to {tsa_url} failed: {exc}") from exc
    if "timestamp-reply" not in content_type:
        raise TimestampError(f"unexpected TSA response type: {content_type!r}")
    if not token:
        raise TimestampError("TSA returned an empty token")
    tsr_path.write_bytes(token)


def verify_token(tsq_path: Path, tsr_path: Path, ca_path: Path) -> None:
    result = _openssl(
        "ts",
        "-verify",
        "-in",
        str(tsr_path),
        "-queryfile",
        str(tsq_path),
        "-CAfile",
        str(ca_path),
    )
    if result.returncode != 0 or "Verification: OK" not in (result.stdout + result.stderr):
        detail = (result.stdout + result.stderr).strip()
        raise TimestampError(f"timestamp verification failed: {detail}")


def describe_token(tsr_path: Path) -> str:
    result = _openssl("ts", "-reply", "-in", str(tsr_path), "-text")
    text = result.stdout + result.stderr
    lines = [line.strip() for line in text.splitlines()]
    wanted = ("Status:", "Time stamp:", "Serial number:", "TSA:")
    return "\n".join(line for line in lines if line.startswith(wanted))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RFC 3161 timestamp for release artifacts")
    parser.add_argument("--files", nargs="+", required=True, help="artifacts to stamp")
    parser.add_argument("--out-dir", required=True, help="directory for manifest and token")
    parser.add_argument(
        "--tsa-url",
        default=FREE_TSA_URL,
        help=f"TSA endpoint (default: {FREE_TSA_URL})",
    )
    parser.add_argument(
        "--ca-url",
        default=FREE_TSA_CA_URL,
        help=f"TSA root CA URL (default: {FREE_TSA_CA_URL})",
    )
    parser.add_argument(
        "--ca-sha256",
        default=FREE_TSA_CA_SHA256,
        help="pinned SHA-256 of the TSA root CA",
    )
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        artifacts = collect_artifacts([Path(f) for f in args.files], out_dir)
        manifest = write_manifest(artifacts, out_dir)
        tsq_path = out_dir / f"{MANIFEST_NAME}.tsq"
        tsr_path = out_dir / f"{MANIFEST_NAME}.tsr"
        ca_path = out_dir / "freetsa-cacert.pem"
        fetch_ca(args.ca_url, args.ca_sha256, ca_path, args.timeout)
        create_query(manifest, tsq_path)
        request_token(tsq_path, tsr_path, args.tsa_url, args.timeout)
        verify_token(tsq_path, tsr_path, ca_path)
    except TimestampError as exc:
        print(f"RFC 3161 stamp FAILED: {exc}", file=sys.stderr)
        return 1

    print(f"RFC 3161 stamp OK: {len(artifacts)} artifacts -> {manifest.name}")
    print(describe_token(tsr_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
