"""CuratorKIT adapter: MAREF red-team dataset -> Alpaca shape.

CuratorKIT expects instruction/input/output (Alpaca) or conversations
(ShareGPT). The MAREF sets use {id, category, prompt, expect}, so we map
prompt -> instruction and expect -> output, keeping id/category as extra
keys for the dataset card.

Empty prompts return None so CuratorKIT records them in rejected.jsonl
rather than silently dropping them.
"""

from __future__ import annotations

from typing import Any


def to_alpaca(row: dict[str, Any]) -> dict[str, Any] | None:
    prompt = str(row.get("prompt") or "").strip()
    if not prompt:
        return None
    return {
        "instruction": prompt,
        "input": "",
        "output": str(row.get("expect") or "n/a"),
        "id": row.get("id"),
        "category": row.get("category"),
    }
