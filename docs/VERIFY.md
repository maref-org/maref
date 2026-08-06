# MAREF Audit Chain Verification Guide

This document describes how to verify the integrity of MAREF's audit chain
independently — without running the MAREF framework itself.

## Overview

MAREF's audit chain provides three layers of integrity verification:

1. **Chain integrity** — each entry's `chain_hash` links it to the previous
   entry, forming an append-only log (`governance/audit.py`)
2. **Signature integrity** — each entry is signed with Ed25519 (v0.38.0+) or
   HMAC-SHA256 (v0.37.0), proving the signer's identity
3. **Merkle integrity** — entries are hashed into a Merkle tree, producing a
   root hash that summarizes the entire log (`eivl/merkle_auditor.py`)
4. **Federated integrity** — multiple organizations' Merkle roots are
   aggregated into a single Federated Root, enabling cross-org verification
   (`eivl/federated_merkle.py`)

---

## 1. Verify Chain Integrity

The audit file is a JSONL file (one JSON object per line). Each entry contains:

```json
{
  "id": "a1b2c3d4",
  "timestamp": 1720000000.0,
  "event_type": "governance_decision",
  "actor": "GovernanceOverlay",
  "action": "approve",
  "details": "Decision approved",
  "metadata": {},
  "previous_hash": "abc...",
  "chain_hash": "def...",
  "ed25519_signature": "sig...",
  "signer_fingerprint": "fp..."
}
```

To verify chain integrity manually:

```python
import hashlib, json

def verify_chain(filepath):
    with open(filepath) as f:
        entries = [json.loads(line) for line in f if line.strip()]

    previous = ""
    for entry in entries:
        if entry.get("previous_hash") != previous:
            return False, f"Chain broken at {entry['id']}"
        payload = json.dumps({
            "id": entry["id"], "timestamp": entry["timestamp"],
            "event_type": entry["event_type"], "actor": entry["actor"],
            "action": entry["action"], "details": entry["details"],
            "metadata": entry.get("metadata", {}),
            "previous_hash": entry.get("previous_hash", ""),
        }, sort_keys=True, ensure_ascii=False, default=str)
        expected = hashlib.sha256(
            entry.get("previous_hash", "").encode() + payload.encode()
        ).hexdigest()
        if entry.get("chain_hash") != expected:
            return False, f"Hash mismatch at {entry['id']}"
        previous = entry["chain_hash"]
    return True, f"All {len(entries)} entries verified"
```

---

## 2. Verify Ed25519 Signature

Each entry (v0.38.0+) is signed with Ed25519. To verify an entry's signature:

```python
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature
import json

def verify_entry_signature(entry, public_key_pem):
    pubkey = serialization.load_pem_public_key(public_key_pem.encode())
    payload = json.dumps({
        "id": entry["id"], "timestamp": entry["timestamp"],
        "event_type": entry["event_type"], "actor": entry["actor"],
        "action": entry["action"], "details": entry["details"],
        "metadata": entry.get("metadata", {}),
        "previous_hash": entry.get("previous_hash", ""),
    }, sort_keys=True, ensure_ascii=False, default=str).encode()
    try:
        pubkey.verify(bytes.fromhex(entry["ed25519_signature"]), payload)
        return True
    except InvalidSignature:
        return False
```

The public key fingerprint in `signer_fingerprint` is `SHA256(raw_pubkey)[:16]`.
It identifies *which* key signed the entry but is not a security boundary —
always verify against the actual public key PEM.

---

## 3. Verify Merkle Proof

Given a Merkle proof from `MerkleAuditor.generate_proof()`, verify offline:

```python
import hashlib

def merkle_hash_pair(left, right):
    return hashlib.sha256((left + right).encode()).hexdigest()

def verify_merkle_proof(target_hash, proof_path, root_hash):
    current = target_hash
    for sibling_hash, direction in proof_path:
        if direction == "left":
            current = merkle_hash_pair(sibling_hash, current)
        else:
            current = merkle_hash_pair(current, sibling_hash)
    return current == root_hash
```

This needs no network access — only the proof and the root hash.

---

## 4. Verify Federated Inclusion

Given a `FederatedProof` from `FederatedMerkleAggregator`, verify that an
organization's Merkle root is included in the federated root:

```python
def verify_federated_proof(org_root_hash, proof_path, federated_root_hash):
    current = org_root_hash
    for sibling_hash, direction in proof_path:
        if direction == "left":
            current = merkle_hash_pair(sibling_hash, current)
        else:
            current = merkle_hash_pair(current, sibling_hash)
    return current == federated_root_hash
```

The proof can also be signed with Ed25519 for non-repudiation:
`FederatedProof.sign(keypair)` and `FederatedProof.verify_signature(pubkey_pem)`.

---

## 5. Full Verification Script

A standalone script that verifies all four layers:

```bash
python3 scripts/verify_audit_chain.py \
    --audit-file /path/to/audit.jsonl \
    --public-key /path/to/signer.pem \
    --merkle-root abcdef... \
    --federated-root fedcba...
```

(This script is at `scripts/verify_audit_chain.py` in the MAREF repository.)

---

## 6. Verification Without MAREF Dependencies

All verification code above uses only Python standard library (`hashlib`, `json`)
plus `cryptography` (for Ed25519). You can extract the verification functions
and run them in any Python 3.10+ environment without installing MAREF.

---

## See Also

- `src/maref/governance/audit.py` — AuditLogger implementation
- `src/maref/eivl/merkle_auditor.py` — Merkle tree audit chain
- `src/maref/eivl/federated_merkle.py` — Federated Merkle aggregation
- `src/maref/crypto/ed25519_keys.py` — Ed25519 key management
