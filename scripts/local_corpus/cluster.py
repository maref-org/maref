"""Offline signature clustering (W2).

Signatures are grouped by token overlap within the same error class. The
algorithm is deterministic, dependency-free and explainable: Jaccard over
identifier tokens plus union-find.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter
from typing import Any

from .normalize import sha16

_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_.]{3,}")
_EXCEPTION = re.compile(r"\b([A-Z][A-Za-z]*(?:Error|Exception|Warning))\b")
_EXIT = re.compile(r"exit (?:code|status)\s*[:=]?\s*(\d+)", re.IGNORECASE)
_CANONICAL = {
    "timeout",
    "permission",
    "network",
    "oom",
    "user_correction",
    "governance_denial",
    "hitl",
    "lint",
    "exception",
}
_STOP = {
    "error",
    "errors",
    "failed",
    "failure",
    "with",
    "from",
    "that",
    "this",
    "have",
    "been",
    "file",
    "line",
    "code",
    "command",
    "exit",
    "status",
    "output",
    "true",
    "false",
    "none",
    "null",
    "test",
    "tests",
}


def tokens(text: str) -> set[str]:
    cleaned = re.sub(r"<path>|<n>|<hex>", " ", (text or "").lower())
    return {
        token.strip("._")
        for token in _TOKEN.findall(cleaned)
        if token.strip("._") and token not in _STOP
    }


def anchor(error_class: str, text: str) -> str:
    """Coarse root-cause family for a signature (level 1)."""
    match = _EXCEPTION.search(text or "")
    if match:
        return match.group(1).lower()
    low = (text or "").lower()
    if "command not found" in low:
        return "command_not_found"
    if "no such file" in low:
        return "no_such_file"
    exit_match = _EXIT.search(low)
    if exit_match:
        return f"exit_{exit_match.group(1)}"
    if error_class in _CANONICAL:
        return error_class
    return "generic"


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    union = len(a | b)
    return len(a & b) / union if union else 0.0


def _load(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT s.sig, s.count, s.runtimes_json, s.example_episode,
               e.error_class, e.snippet
        FROM signature s LEFT JOIN episode e ON e.id = s.example_episode
        ORDER BY s.count DESC
        """
    ).fetchall()
    return [
        {
            "sig": str(row["sig"]),
            "count": int(row["count"]),
            "runtimes": json.loads(row["runtimes_json"] or "[]"),
            "example": str(row["example_episode"] or ""),
            "error_class": str(row["error_class"] or "unknown"),
            "snippet": str(row["snippet"] or ""),
            "tokens": tokens(str(row["snippet"] or "")),
            "family": anchor(str(row["error_class"] or "unknown"), str(row["snippet"] or "")),
        }
        for row in rows
    ]


def _components(items: list[dict[str, Any]], threshold: float, min_shared: int) -> list[list[int]]:
    parent = list(range(len(items)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if (
                items[i]["family"] != items[j]["family"]
                or items[i]["error_class"] != items[j]["error_class"]
            ):
                continue
            a, b = items[i]["tokens"], items[j]["tokens"]
            shared = len(a & b)
            if shared < min_shared and min(len(a), len(b)) > min_shared:
                continue
            if _jaccard(a, b) >= threshold:
                union(i, j)
    groups: dict[int, list[int]] = {}
    for index in range(len(items)):
        groups.setdefault(find(index), []).append(index)
    return list(groups.values())


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS family (
            id                TEXT PRIMARY KEY,
            error_class       TEXT NOT NULL,
            anchor            TEXT NOT NULL,
            episode_count     INTEGER DEFAULT 0,
            signatures        INTEGER DEFAULT 0,
            runtimes_json     TEXT DEFAULT '[]',
            example_episode   TEXT DEFAULT ''
        );
        """
    )
    columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(cluster)")}
    if columns and "family_id" not in columns:
        conn.execute("ALTER TABLE cluster ADD COLUMN family_id TEXT DEFAULT ''")
    conn.commit()


def build_clusters(
    conn: sqlite3.Connection, threshold: float = 0.55, min_shared: int = 2
) -> dict[str, int]:
    items = _load(conn)
    _ensure_schema(conn)
    conn.execute("DELETE FROM cluster")
    conn.execute("DELETE FROM family")
    families: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in items:
        families.setdefault((item["error_class"], item["family"]), []).append(item)
    for (error_class, family_name), members in families.items():
        runtimes = sorted({runtime for member in members for runtime in member["runtimes"]})
        example = max(members, key=lambda m: m["count"])["example"]
        conn.execute(
            "INSERT OR REPLACE INTO family(id, error_class, anchor, episode_count,"
            " signatures, runtimes_json, example_episode) VALUES(?,?,?,?,?,?,?)",
            (
                sha16("family", error_class, family_name),
                error_class,
                family_name,
                sum(member["count"] for member in members),
                len(members),
                json.dumps(runtimes),
                example,
            ),
        )
    groups = _components(items, threshold, min_shared)
    created = 0
    for indexes in groups:
        members = [items[i] for i in indexes]
        first = min(members, key=lambda m: m["sig"])
        cluster_id = sha16(first["error_class"], *sorted(m["sig"] for m in members))
        counter: Counter[str] = Counter()
        for member in members:
            counter.update(member["tokens"])
        runtimes = sorted({runtime for member in members for runtime in member["runtimes"]})
        example = max(members, key=lambda m: m["count"])["example"]
        episode_count = sum(member["count"] for member in members)
        label = " ".join(token for token, _ in counter.most_common(4))
        conn.execute(
            """
            INSERT OR REPLACE INTO cluster(
                id, error_class, label, signatures, episode_count,
                runtimes_json, signatures_json, example_episode, family_id
            ) VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (
                cluster_id,
                first["error_class"],
                label,
                len(members),
                episode_count,
                json.dumps(runtimes),
                json.dumps(sorted(m["sig"] for m in members)),
                example,
                sha16("family", first["error_class"], first["family"]),
            ),
        )
        created += 1
    conn.commit()
    return {
        "clusters": created,
        "families": len(families),
        "signatures": len(items),
    }


def top_clusters(conn: sqlite3.Connection, limit: int = 15) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM cluster ORDER BY episode_count DESC, signatures DESC LIMIT ?", (limit,)
    ).fetchall()
    return [
        {
            "id": row["id"],
            "error_class": row["error_class"],
            "label": row["label"],
            "signatures": int(row["signatures"]),
            "episodes": int(row["episode_count"]),
            "runtimes": json.loads(row["runtimes_json"] or "[]"),
        }
        for row in rows
    ]


def cross_runtime_clusters(conn: sqlite3.Connection, limit: int = 15) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM cluster WHERE json_array_length(runtimes_json) >= 2"
        " ORDER BY episode_count DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [
        {
            "id": row["id"],
            "error_class": row["error_class"],
            "label": row["label"],
            "signatures": int(row["signatures"]),
            "episodes": int(row["episode_count"]),
            "runtimes": json.loads(row["runtimes_json"] or "[]"),
        }
        for row in rows
    ]


def top_families(conn: sqlite3.Connection, limit: int = 15) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM family ORDER BY episode_count DESC, signatures DESC LIMIT ?", (limit,)
    ).fetchall()
    return [
        {
            "id": row["id"],
            "error_class": row["error_class"],
            "anchor": row["anchor"],
            "signatures": int(row["signatures"]),
            "episodes": int(row["episode_count"]),
            "runtimes": json.loads(row["runtimes_json"] or "[]"),
        }
        for row in rows
    ]
