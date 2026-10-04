#!/usr/bin/env python3
"""Standalone audit chain verification script.

Verifies all four layers of MAREF audit chain integrity without requiring
the MAREF framework to be installed. Only needs Python 3.10+ standard
library + cryptography package for Ed25519 verification.

Usage:
    # Verify chain integrity only
    python3 scripts/verify_audit_chain.py --audit-file audit.jsonl

    # HMAC 链（state_machine / AuditEntry 写入器）自动解析密钥:
    #   MAREF_HMAC_SECRET_KEY / MAREF_HMAC_KEY_FILE / <runtime>/.maraf_hmac_key
    python3 scripts/verify_audit_chain.py --audit-file audit.jsonl --auto-hmac-key

    # Verify chain + Ed25519 signatures
    python3 scripts/verify_audit_chain.py \\
        --audit-file audit.jsonl --public-key signer.pem

    # Verify chain + Merkle proof
    python3 scripts/verify_audit_chain.py \\
        --audit-file audit.jsonl --merkle-proof proof.json

    # For federated proof verification, use:
    #   maref federated verify proof.json [--pubkey signer.pem]

Exit codes: 0=PASS 1=BROKEN 3=UNRECOGNIZED 4=NO_CHAIN 5=NEEDS_KEY 6=PARTIAL 7=SEGMENTED
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
from pathlib import Path

_HASH_ALGOS = {
    "sha256": hashlib.sha256,
    "sha512": hashlib.sha512,
    "sha1": hashlib.sha1,
    "md5": hashlib.md5,
}
_SIG_KEYS = ("hmac", "hmac_signature", "signature")

# 退出码语义（供 evidence_gate / CI 区分「真断链」与「工具不认识」）
EXIT_PASS = 0
EXIT_BROKEN = 1        # prev_hash 断点 或 已知算法下哈希不匹配
EXIT_UNRECOGNIZED = 3  # 算法/payload 构造无法识别（不等同于被篡改）
EXIT_NO_CHAIN = 4      # 条目无链字段（如 hooks 仅 hmac）
EXIT_NEEDS_KEY = 5     # 疑似 HMAC 链但未提供密钥
EXIT_PARTIAL = 6       # 混合链：部分条目可验证，前段写入器算法未知
EXIT_SEGMENTED = 7     # 分段重启：写入方漏传 previous_hash（非篡改）


def _repo_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def _runtime_dir() -> Path:
    env = os.environ.get("MAREF_RUNTIME_DIR")
    if env:
        return Path(env)
    try:
        cfg = json.loads((Path.home() / ".maref" / "runtime_dir.json").read_text())
        cand = cfg.get("runtime_dir")
        if cand and Path(cand).is_dir():
            return Path(cand)
    except (OSError, ValueError, TypeError):
        pass
    return _repo_dir()


def resolve_hmac_key() -> bytes | None:
    """解析 HMAC 密钥（与 openclaw scripts/audit_heartbeat.py 同源顺序）。

    MAREF_HMAC_SECRET_KEY > MAREF_HMAC_KEY_FILE > <runtime>/.maraf_hmac_key
    > <repo>/.maraf_hmac_key > ~/.maref.env
    """
    env_key = os.environ.get("MAREF_HMAC_SECRET_KEY", "").strip()
    if env_key:
        return env_key.encode("utf-8")
    file_key = os.environ.get("MAREF_HMAC_KEY_FILE", "").strip()
    candidates = [Path(file_key)] if file_key else []
    candidates += [
        _runtime_dir() / ".maraf_hmac_key",
        _repo_dir() / ".maraf_hmac_key",
        Path.home() / ".maref.env",
    ]
    for cand in candidates:
        if not cand.exists():
            continue
        try:
            if cand.suffix == ".env" or cand.name.endswith(".env"):
                for line in cand.read_text().splitlines():
                    if line.startswith("MAREF_HMAC_SECRET_KEY="):
                        v = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if v:
                            return v.encode("utf-8")
            else:
                v = cand.read_text().strip()
                if v:
                    return v.encode("utf-8")
        except OSError:
            continue
    return None


def _payload_variants(entry: dict) -> dict[str, str]:
    """候选 payload 构造（对应历史多个写入器的序列化差异）。"""
    sig = set(_SIG_KEYS)
    kept = [k for k in entry if k != "chain_hash" and k not in sig]
    std_keys = [
        k
        for k in ("id", "timestamp", "event_type", "actor", "action", "details", "metadata", "previous_hash")
        if k in entry
    ]
    dumps = lambda obj, sort: json.dumps(  # noqa: E731
        obj, sort_keys=sort, ensure_ascii=False, default=str
    )
    out = {
        "std_sorted": dumps({k: entry.get(k) for k in std_keys}, True),
        "all_sorted": dumps({k: entry[k] for k in sorted(kept)}, True),
        "all_insertion": dumps({k: entry[k] for k in kept}, False),
    }
    # AuditEntry._payload_for_signing 变体: 恒 8 键 (previous_hash 空串也写入,
    # 但 to_dict 省略空键 → 条件 std_keys 对首条会漏键) + layer (dataclass 默认
    # "governance", to_dict 不输出该键但参与 hash)。T2-2 闭环 append 后由本候选识别。
    base8 = {
        k: entry.get(k)
        for k in (
            "id", "timestamp", "event_type", "actor",
            "action", "details", "metadata",
        )
    }
    # 首条 previous_hash 为空时 to_dict 省略键 → get()=None, 真实 payload 是 ""
    base8["previous_hash"] = entry.get("previous_hash") or ""
    out["std_layer_sorted"] = dumps(
        {**base8, "layer": entry.get("layer") or "governance"}, True
    )
    if len(std_keys) != len(kept):
        out["std_noprev_sorted"] = dumps(
            {k: entry.get(k) for k in std_keys if k != "previous_hash"}, True
        )
    return out


def _digest_one(entry: dict, algo: str, hmac_key: bytes | None = None) -> str | None:
    """按 `payload|algoname|position` 计算单个 digest；不可算返回 None。"""
    try:
        pname, aname, pos = algo.split("|")
    except ValueError:
        return None
    payload = _payload_variants(entry).get(pname)
    if payload is None:
        return None
    body = payload.encode()
    if aname == "hmac_sha256":
        if not hmac_key:
            return None
        return hmac.new(hmac_key, body, hashlib.sha256).hexdigest()
    fn = _HASH_ALGOS.get(aname)
    if fn is None:
        return None
    if pos == "payload_only":
        return fn(body).hexdigest()
    prev_b = str(entry.get("previous_hash", "")).encode()
    return fn(prev_b + body).hexdigest() if pos == "prev_first" else fn(body + prev_b).hexdigest()


def _candidate_digests(entry: dict, hmac_key: bytes | None = None) -> dict[str, str]:
    """(算法名 → digest)，命名格式: payload|algo|prev_position。"""
    prev = str(entry.get("previous_hash", ""))
    prev_b = prev.encode()
    out: dict[str, str] = {}
    for pname, payload in _payload_variants(entry).items():
        body = payload.encode()
        for aname, fn in _HASH_ALGOS.items():
            out[f"{pname}|{aname}|prev_first"] = fn(prev_b + body).hexdigest()
            out[f"{pname}|{aname}|payload_first"] = fn(body + prev_b).hexdigest()
            out[f"{pname}|{aname}|payload_only"] = fn(body).hexdigest()
        if hmac_key:
            # AuditEntry/state_machine 写入器: chain_hash = HMAC-SHA256(key, payload)
            out[f"{pname}|hmac_sha256|payload_only"] = hmac.new(
                hmac_key, body, hashlib.sha256
            ).hexdigest()
    return out


def _sniff(entries: list[dict], hmac_key: bytes | None = None) -> str | None:
    """用前若干条目嗅探该链的哈希算法构造；全部失配返回 None。"""
    scored: dict[str, int] = {}
    probes = [e for e in entries if e.get("chain_hash")][:3]
    for entry in probes:
        cands = _candidate_digests(entry, hmac_key)
        want = entry.get("chain_hash", "")
        hit = [k for k, v in cands.items() if v == want]
        if not hit:
            continue
        # 首条 previous_hash 可能为空 → 优先能同时解释第 2 条的构造
        scored[hit[0]] = scored.get(hit[0], 0) + 1
    if not scored:
        # 再用含非空 previous_hash 的条目复核
        for entry in entries:
            if not entry.get("previous_hash"):
                continue
            cands = _candidate_digests(entry, hmac_key)
            hit = [k for k, v in cands.items() if v == entry.get("chain_hash", "")]
            if hit:
                scored[hit[0]] = scored.get(hit[0], 0) + 1
                break
        else:
            return None
    return max(scored, key=lambda k: scored[k])


def _prev_of(entry: dict) -> str:
    """previous_hash 归一化（null/缺失 → ""）。"""
    v = entry.get("previous_hash")
    return v if isinstance(v, str) and v else ""


def _link_of(entry: dict) -> str:
    """链的推进值：chain_hash；无 chain_hash 的写入器（如 meta_cognitive_audit）
    用 id 顶位 —— 与 audit_heartbeat `prev.get('chain_hash', prev.get('id',''))` 同构。"""
    v = entry.get("chain_hash")
    if isinstance(v, str) and v:
        return v
    v = entry.get("id")
    return v if isinstance(v, str) else ""


def _load(path: str) -> tuple[list[dict], int]:
    entries, bad = [], 0
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                bad += 1
    return entries, bad


def verify_chain(
    filepath: str, hmac_key: bytes | None = None, strict: bool = False
) -> tuple[str, str]:
    """返回 (status, message)；status ∈ PASS/BROKEN/UNRECOGNIZED/NEEDS_KEY/NO_CHAIN/EMPTY。"""
    entries, bad_json = _load(filepath)
    if not entries:
        return "EMPTY", "Empty audit file"

    has_chain = sum(1 for e in entries if "chain_hash" in e)
    if has_chain == 0:
        fields = sorted(entries[0].keys())
        return (
            "NO_CHAIN",
            f"No chain_hash fields (schema={fields}); 仅 hmac 的链请用 --hmac-key 校验",
        )

    # 1) previous_hash 连续性（与算法无关的事实）
    #    prev 被清空 = 写入方漏传 → 分段重启(不是篡改)；prev 非空但不等 = 真断链
    hard_breaks: list[int] = []
    resets: list[int] = []
    prev = ""
    for i, e in enumerate(entries):
        cp = _prev_of(e)
        if cp != prev and i > 0:
            (resets if cp == "" else hard_breaks).append(i)
        prev = _link_of(e) or prev
    if hard_breaks:
        first = hard_breaks[0]
        return (
            "BROKEN",
            f"Chain broken at entry #{first} id={entries[first].get('id', '?')} "
            f"(prev_hash mismatch (non-empty but wrong), {len(hard_breaks)} break(s)"
            + (f", +{bad_json} unparseable" if bad_json else "")
            + ")",
        )
    segmented = bool(resets)

    # 2) 哈希构造识别
    algo = None
    probe = next((e for e in entries if e.get("chain_hash")), None)
    if probe:
        want = probe.get("chain_hash", "")
        default = _candidate_digests(probe, hmac_key)
        if default.get("std_sorted|sha256|prev_first") == want:
            algo = "std_sorted|sha256|prev_first"
        else:
            algo = _sniff(entries, hmac_key)

    if algo is None and hmac_key is None:
        fields = sorted((probe or {}).keys())
        return (
            "NEEDS_KEY",
            f"Unrecognized hash construction (schema fields={fields}); "
            "state_machine/AuditEntry 链为 HMAC-SHA256(key, payload) — 请提供 "
            "--hmac-key / MAREF_HMAC_KEY_FILE 以判定 篡改 vs 写入器差异",
        )
    if algo is None:
        fields = sorted((probe or {}).keys())
        return (
            "UNRECOGNIZED",
            f"Unrecognized hash construction even with hmac key (schema fields={fields}); "
            "cannot judge tamper vs writer-version drift",
        )

    # 3) 全链校验：主算法快路径 + 全候选 fallback
    #    多写入器混合链中「哈希对不上」≠「被篡改」→ 默认只把
    #    prev 非空且错误 判 BROKEN，其余归入 unverified（需对照写入方源码定性）；
    #    --strict 下 PARTIAL 升级为 BROKEN（用于 CI 门禁）。
    prev = ""
    verified = 0
    unverified = 0
    first_unverified_id = None
    algo_counts: dict[str, int] = {}
    for i, e in enumerate(entries):
        cur_prev = _prev_of(e)
        # 首条可能续自文件外的历史链；段重启（prev 被清空）也不判错
        if i > 0 and cur_prev and cur_prev != prev:
            return (
                "BROKEN",
                f"Chain broken at entry {e.get('id', i)} (previous_hash non-empty but wrong)",
            )
        want = e.get("chain_hash")
        if want:
            hit = None
            if algo and _digest_one(e, algo, hmac_key) == want:
                hit = algo
            if hit is None:
                for k, v in _candidate_digests(e, hmac_key).items():
                    if v == want:
                        hit = k
                        break
            if hit:
                verified += 1
                algo_counts[hit] = algo_counts.get(hit, 0) + 1
            else:
                unverified += 1
                if first_unverified_id is None:
                    first_unverified_id = str(e.get("id", i))
        prev = _link_of(e) or prev

    suffix = f", +{bad_json} unparseable" if bad_json else ""
    algos_desc = (
        ", ".join(
            f"{k}×{v}"
            for k, v in sorted(algo_counts.items(), key=lambda x: -x[1])[:3]
        )
        or "-"
    )
    if verified == 0:
        return (
            "UNRECOGNIZED",
            f"0/{len(entries)} entries verifiable — no known construction matches "
            f"({unverified} unverifiable); cannot judge tamper vs writer-version drift"
            + suffix,
        )
    if segmented:
        return (
            "SEGMENTED",
            f"{verified}/{len(entries)} verified (algos: {algos_desc}), "
            f"chain segmented: {len(resets)}× previous_hash cleared "
            f"(first at #{resets[0]} id={entries[resets[0]].get('id', '?')}) — "
            "根因: 写入方漏传 previous_hash (分段重启，非篡改)"
            + suffix,
        )
    if unverified:
        if strict:
            return (
                "BROKEN",
                f"[strict] {unverified} entries unverifiable after verified segment "
                f"(first id={first_unverified_id}; algos={algos_desc})"
                + suffix,
            )
        return (
            "PARTIAL",
            f"{verified}/{len(entries)} entries verified (algos: {algos_desc}), "
            f"{unverified} unverifiable (from id={first_unverified_id}; "
            "需对照写入方源码区分 算法漂移 vs 篡改)"
            + suffix,
        )
    return "PASS", f"All {len(entries)} entries verified (algos: {algos_desc}{suffix})"



def verify_ed25519_signatures(filepath: str, public_key_pem_path: str) -> tuple[int, int]:
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (  # noqa: F401
            Ed25519PublicKey,
        )
    except ImportError:
        print("Error: 'cryptography' package required for Ed25519 verification", file=sys.stderr)
        print("Install: pip install cryptography", file=sys.stderr)
        sys.exit(1)

    pubkey_pem = Path(public_key_pem_path).read_text()
    pubkey = serialization.load_pem_public_key(pubkey_pem.encode())

    with open(filepath) as f:
        entries = [json.loads(line) for line in f if line.strip()]

    valid = 0
    total = 0
    for entry in entries:
        sig = entry.get("ed25519_signature", "")
        if not sig:
            continue
        total += 1
        payload = json.dumps(
            {
                "id": entry["id"],
                "timestamp": entry["timestamp"],
                "event_type": entry["event_type"],
                "actor": entry["actor"],
                "action": entry["action"],
                "details": entry["details"],
                "metadata": entry.get("metadata", {}),
                "previous_hash": entry.get("previous_hash", ""),
            },
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        ).encode()
        try:
            pubkey.verify(bytes.fromhex(sig), payload)
            valid += 1
        except InvalidSignature:
            pass

    return valid, total


def merkle_hash_pair(left: str, right: str) -> str:
    return hashlib.sha256((left + right).encode()).hexdigest()


def verify_merkle_proof(target_hash: str, proof: list[list[str | bool]], expected_root: str) -> bool:
    current = target_hash
    for sibling_hash, direction in proof:
        if direction == "left" or direction is False:
            current = merkle_hash_pair(sibling_hash, current)
        else:
            current = merkle_hash_pair(current, sibling_hash)
    return current == expected_root


def verify_merkle_proof_file(proof_path: str) -> tuple[bool, str]:
    with open(proof_path) as f:
        data = json.load(f)

    target = data.get("target_hash", data.get("leaf_hash", ""))
    proof_path_list = data.get("proof_path", data.get("proof", []))
    root = data.get("root_hash", data.get("merkle_root", ""))

    if not target:
        return False, "Missing target_hash/leaf_hash in proof file"
    if not proof_path_list:
        return False, "Missing proof_path/proof in proof file"
    if not root:
        return False, "Missing root_hash/merkle_root in proof file"

    ok = verify_merkle_proof(target, proof_path_list, root)
    if ok:
        return True, f"Merkle proof valid: {target[:12]}... → {root[:12]}..."
    return False, f"Merkle proof invalid: {target[:12]}... does not chain to {root[:12]}..."


def main():
    parser = argparse.ArgumentParser(
        description="Verify MAREF audit chain integrity"
    )
    parser.add_argument("--audit-file", required=True, help="Path to audit JSONL file")
    parser.add_argument(
        "--public-key",
        default=None,
        help="Path to Ed25519 public key PEM (for signature verification)",
    )
    parser.add_argument(
        "--merkle-proof",
        default=None,
        help="Path to Merkle proof JSON file (for offline proof verification)",
    )
    parser.add_argument(
        "--no-hmac-key",
        action="store_true",
        help="禁用自动 HMAC 密钥解析（默认会尝试 env/keyfile 以验证 HMAC 链）",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="严格模式：无法用已知构造验证的条目直接判 BROKEN（用于 CI 门禁）",
    )
    args = parser.parse_args()

    if not Path(args.audit_file).exists():
        print(f"Error: audit file not found: {args.audit_file}", file=sys.stderr)
        sys.exit(1)

    hmac_key = None if args.no_hmac_key else resolve_hmac_key()
    status, msg = verify_chain(args.audit_file, hmac_key=hmac_key, strict=args.strict)
    icon = {"PASS": "✅", "PARTIAL": "⚠️", "SEGMENTED": "⚠️"}.get(status, "❌")
    print(f"{icon} Chain integrity [{status}]: {msg}")
    exit_map = {
        "PASS": EXIT_PASS,
        "PARTIAL": EXIT_PARTIAL,
        "SEGMENTED": EXIT_SEGMENTED,
        "BROKEN": EXIT_BROKEN,
        "UNRECOGNIZED": EXIT_UNRECOGNIZED,
        "NO_CHAIN": EXIT_NO_CHAIN,
        "EMPTY": EXIT_NO_CHAIN,
        "NEEDS_KEY": EXIT_NEEDS_KEY,
    }
    if status == "PASS":
        pass  # 继续可选的 Ed25519 / Merkle 校验
    elif status in ("PARTIAL", "SEGMENTED"):
        sys.exit(exit_map[status])
    else:
        sys.exit(exit_map.get(status, EXIT_BROKEN))

    if args.public_key:
        valid, total = verify_ed25519_signatures(args.audit_file, args.public_key)
        if total > 0:
            print(f"{'✅' if valid == total else '⚠️'} Ed25519 signatures: {valid}/{total} valid")
        else:
            print("ℹ️  No Ed25519-signed entries found")

    if args.merkle_proof:
        if not Path(args.merkle_proof).exists():
            print(f"Error: proof file not found: {args.merkle_proof}", file=sys.stderr)
            sys.exit(1)
        ok, msg = verify_merkle_proof_file(args.merkle_proof)
        print(f"{'✅' if ok else '❌'} Merkle proof: {msg}")
        if not ok:
            sys.exit(1)

    print("\nVerification complete.")


if __name__ == "__main__":
    main()
