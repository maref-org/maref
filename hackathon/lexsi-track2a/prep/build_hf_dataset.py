#!/opt/homebrew/bin/python3
"""把 Lexsi 攻击/良性语料规范化成可直接 load_dataset 的 HF 数据集（G1）。

动机（2026-11-18）：
现有 HF 数据集 `maref-org/lexsi-redteam-set` 是裸 jsonl 平铺，`language: en` 单一、
无 splits/features、无 datasheet。HF 是本次赛事共同主办方，若想被 "featured"，
数据集必须能被一行代码消费，而不是让人自己挑文件。

产出（默认写到 prep/hf_dataset/，不自动上传）：
  data/prompts-dev.parquet
  data/prompts-control.parquet
  data/prompts-holdout_v1.parquet
  data/prompts-holdout_v2.parquet
  data/multi_turn.parquet
  README.md      # HF dataset card（YAML front matter + 说明）
  DATASHEET.md   # Gebru 七段式数据说明书
  manifest.json  # 行数统计 + 各源文件 sha256 + 泄漏校验结果

安全约束：
- 只做结构化，不改 prompt 文本、不改 expect 标签（任何改动都会让已公开数字失真）
- 泄漏校验：dev 与 holdout 的 id / prompt 必须两两不交，不通过直接非零退出

用法：
  /opt/homebrew/bin/python3 prep/build_hf_dataset.py            # 构建 + 校验
  /opt/homebrew/bin/python3 prep/build_hf_dataset.py --check    # 只校验不写盘
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "hf_dataset"

# (源文件, split 名, 说明)
SOURCES = [
    ("redteam_set_v1.jsonl", "dev", "114-prompt red-team dev set (the set behind every published number)"),
    ("benign_set_v2.jsonl", "dev", "60-prompt benign control (over-refusal denominator)"),
    ("benign_encoded.jsonl", "control", "30 encoded-but-benign prompts (false-block control)"),
    ("holdout_v2.jsonl", "holdout_v2", "pre-registered holdout v2 (the fix, verified on a fresh disjoint split)"),
]
# holdout_v1 经实测是 dev 的 30/30 子集（id 与 prompt 全部重合），
# 不能当独立 split —— 那样会让下载者把它当真 holdout 用，等于泄漏。
# 正确做法：作为 dev 上的布尔标记列 `holdout_v1`。
SUBSET_FLAG = ("holdout_v1.jsonl", "holdout_v1", "frozen subset of dev (30/174) used for the first read; NOT an independent split")
MULTI_TURN = ("multi_turn_set_v1.jsonl", "multi_turn", "30 multi-turn gradual-escalation conversations")
MULTI_TURN = ("multi_turn_set_v1.jsonl", "multi_turn", "30 multi-turn gradual-escalation conversations")


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    h.update(p.read_bytes())
    return h.hexdigest()


def load_rows(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def normalise(row: dict, split: str, source: str) -> dict:
    """统一成定长 schema；缺字段补空串，绝不改已有值。"""
    return {
        "id": str(row.get("id", "")),
        "prompt": str(row.get("prompt", "")),
        "expect": str(row.get("expect", "")),
        "category": str(row.get("category", "")),
        "encoding": str(row.get("encoding", "")),
        "group": str(row.get("group", "")),
        "plain": str(row.get("plain", "")),
        "acrostic": str(row.get("acrostic", "")),
        "holdout_v1": False,
        "split": split,
        "source": source,
    }


def normalise_multi(row: dict, split: str, source: str) -> dict:
    turns = row.get("turns") or []
    return {
        "id": str(row.get("id", "")),
        "turns": [str(t) for t in turns],
        "n_turns": len(turns),
        "expect": str(row.get("expect", "")),
        "category": str(row.get("category", "")),
        "split": split,
        "source": source,
    }


def apply_subset_flag(splits: dict[str, list[dict]]) -> list[str]:
    """holdout_v1 必须是 dev 的真子集：命中则打标记，未命中即报错（防止悄悄变成独立 split）。"""
    path = HERE / SUBSET_FLAG[0]
    if not path.exists():
        return [f"缺少 {SUBSET_FLAG[0]}（无法验证 holdout_v1 子集关系）"]
    sub_ids = {r["id"] for r in load_rows(path)}
    dev = splits.get("dev", [])
    dev_ids = {r["id"] for r in dev}
    missing = sub_ids - dev_ids
    if missing:
        return [f"{SUBSET_FLAG[0]} 有 {len(missing)} 条不在 dev 中：{sorted(missing)[:5]}"]
    marked = 0
    for r in dev:
        if r["id"] in sub_ids:
            r["holdout_v1"] = True
            marked += 1
    if marked != len(sub_ids):
        return [f"holdout_v1 标记数 {marked} != 子集条数 {len(sub_ids)}"]
    return []


def leak_check(splits: dict[str, list[dict]], multi: list[dict]) -> list[str]:
    """dev/control 与 holdout_v2 之间不得有同 id 或同 prompt。"""
    problems = []
    held: dict[str, str] = {}
    for r in splits.get("holdout_v2", []):
        held[r["id"]] = "holdout_v2"
        held["PROMPT:" + hashlib.sha256(r["prompt"].encode()).hexdigest()] = "holdout_v2"
    for name in ("dev", "control"):
        for r in splits.get(name, []):
            for key in (r["id"], "PROMPT:" + hashlib.sha256(r["prompt"].encode()).hexdigest()):
                if key in held:
                    problems.append(f"泄漏：{name} 的 {r['id']} 与 {held[key]} 冲突")
                    break
    if multi:
        ids = [r["id"] for r in multi]
        if len(ids) != len(set(ids)):
            problems.append("multi_turn 内 id 重复")
    return problems


def build(check_only: bool) -> int:
    splits: dict[str, list[dict]] = {}
    for fname, split, _desc in SOURCES:
        p = HERE / fname
        if not p.exists():
            print(f"[FAIL] 缺少源文件 {p}")
            return 2
        rows = load_rows(p)
        splits.setdefault(split, []).extend(normalise(r, split, fname) for r in rows)
        print(f"  {fname:26s} -> split={split:11s} n={len(rows)}")

    mpath = HERE / MULTI_TURN[0]
    multi = []
    if mpath.exists():
        multi = [normalise_multi(r, MULTI_TURN[1], MULTI_TURN[0]) for r in load_rows(mpath)]
        print(f"  {MULTI_TURN[0]:26s} -> split=multi_turn  n={len(multi)}")

    problems = apply_subset_flag(splits) + leak_check(splits, multi)
    for p in problems:
        print(f"[LEAK] {p}")
    if problems:
        return 1

    total = sum(len(v) for v in splits.values()) + len(multi)
    print(f"[OK] 泄漏校验通过；总条数 {total}")

    if check_only:
        return 0

    import pyarrow as pa
    import pyarrow.parquet as pq

    (OUT / "data").mkdir(parents=True, exist_ok=True)
    schema = pa.schema([
        ("id", pa.string()), ("prompt", pa.string()), ("expect", pa.string()),
        ("category", pa.string()), ("encoding", pa.string()), ("group", pa.string()),
        ("plain", pa.string()), ("acrostic", pa.string()), ("holdout_v1", pa.bool_()),
        ("split", pa.string()), ("source", pa.string()),
    ])
    for split, rows in splits.items():
        tbl = pa.Table.from_pylist(rows, schema=schema)
        pq.write_table(tbl, OUT / "data" / f"prompts-{split}.parquet")
    if multi:
        mschema = pa.schema([
            ("id", pa.string()), ("turns", pa.list_(pa.string())), ("n_turns", pa.int32()),
            ("expect", pa.string()), ("category", pa.string()), ("split", pa.string()),
            ("source", pa.string()),
        ])
        pq.write_table(pa.Table.from_pylist(multi, schema=mschema), OUT / "data" / "multi_turn.parquet")

    manifest = {
        "built_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "builder": "prep/build_hf_dataset.py",
        "counts": {k: len(v) for k, v in splits.items()} | ({"multi_turn": len(multi)} if multi else {}),
        "sources": {f: sha256(HERE / f) for f, _s, _d in SOURCES + [SUBSET_FLAG] if (HERE / f).exists()}
        | ({MULTI_TURN[0]: sha256(mpath)} if mpath.exists() else {}),
        "leak_check": "pass",
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[WRITE] {OUT}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    sys.exit(build(ap.parse_args().check))
