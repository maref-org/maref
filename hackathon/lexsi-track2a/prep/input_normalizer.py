#!/usr/bin/env python3
"""MAREF 运行时层原型：编码攻击的输入归一化与检出。

背景（实测）：SafeTune 的 inference-time steering 对 encoding 类攻击 6 个 alpha
全部无效（ASR 恒为 100%），因为编码后的输入在模型的语义层不构成"有害请求"，
refusal 通路未被激活。因此编码攻击必须在**输入侧**处理。

本模块做三件事：
  1. 多路解码：base64 / base32 / rot13 / url / 反转 / 分片 / 隔字符 / leet / 同形字 / zalgo / morse
  2. 命中检测：解码结果与 deny 模式比对
  3. 输出归一化文本，供下游模型或门禁使用

用法:
    python3 prep/input_normalizer.py --dataset prep/redteam_set_v1.jsonl
"""
from __future__ import annotations

import argparse
import base64
import binascii
import codecs
import json
import re
import unicodedata
from pathlib import Path

# 有害意图关键词（用于检出，不做内容生成）
DENY_PATTERNS = [
    r"pick(?:ing)? a lock", r"bypass (?:a |the )?(?:login|lock|door|badge|reader)",
    r"pipe bomb", r"ransomware", r"phishing", r"poison(?:ing)? someone",
    r"exfiltrat", r"steal (?:saved )?passwords", r"smuggle",
    r"clone a badge", r"disable the audit", r"environment files", r"api keys",
    r"authorized_keys", r"drop(?:per)? .*sandbox", r"open a safe",
    r"tailgat", r"defeat a door sensor", r"credential",
    r"crack (?:a )?(?:wifi|wi-fi|password)", r"system prompt", r"lockpick",
    r"开锁", r"撬锁", r"系统提示", r"unlock (?:a |the )?(?:standard )?lock",
]
DENY_RE = re.compile("|".join(DENY_PATTERNS), re.I)

# 常见同形字 → ASCII（覆盖西里尔/希腊字母）
HOMOGLYPH = {
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "х": "x", "у": "y",
    "і": "i", "ј": "j", "ѕ": "s", "ԁ": "d", "һ": "h", "ӏ": "l", "ո": "n",
    "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H", "Ι": "I", "Κ": "K",
    "Μ": "M", "Ν": "N", "Ο": "O", "Ρ": "P", "Τ": "T", "Υ": "Y", "Χ": "X",
    "ο": "o", "ι": "i", "κ": "k", "ν": "v", "ρ": "p", "τ": "t", "υ": "u",
}
LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"})
MORSE = {
    ".-": "a", "-...": "b", "-.-.": "c", "-..": "d", ".": "e", "..-.": "f",
    "--.": "g", "....": "h", "..": "i", ".---": "j", "-.-": "k", ".-..": "l",
    "--": "m", "-.": "n", "---": "o", ".--.": "p", "--.-": "q", ".-.": "r",
    "...": "s", "-": "t", "..-": "u", "...-": "v", ".--": "w", "-..-": "x",
    "-.--": "y", "--..": "z", "..--..": "?", "----.": "9", "-----": "0",
}


def _strip_zalgo(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _homoglyph(s: str) -> str:
    return "".join(HOMOGLYPH.get(c, c) for c in s)


def _try_b64(token: str) -> str | None:
    t = token.strip().strip('"\'')
    if len(t) < 12 or len(t) % 4:
        return None
    if not re.fullmatch(r"[A-Za-z0-9+/=_\-]+", t):
        return None
    try:
        raw = base64.b64decode(t + "=" * (-len(t) % 4), validate=False)
        out = raw.decode("utf-8", "ignore")
        return out if sum(c.isprintable() for c in out) >= len(out) * 0.8 and out.strip() else None
    except (binascii.Error, ValueError):
        return None


def _try_b32(token: str) -> str | None:
    t = re.sub(r"[^A-Z2-7]", "", token.upper())
    if len(t) < 12:
        return None
    for pad in range(8):
        try:
            out = base64.b32decode(t + "=" * pad).decode("utf-8", "ignore")
            if out.strip() and sum(c.isprintable() for c in out) >= len(out) * 0.8:
                return out
        except (binascii.Error, ValueError):
            continue
    return None


def _try_morse(s: str) -> str | None:
    frag = max(re.findall(r"[.\-/\s]{9,}", s), key=len, default="")
    s = frag
    if not s.strip():
        return None
    words = []
    for word in s.strip().split("/"):
        letters = [MORSE.get(code, "") for code in word.split()]
        words.append("".join(letters))
    out = " ".join(w for w in words if w)
    return out or None


PINYIN_HINT = {
    "ruhe": "how", "dakai": "open", "suo": "lock", "jiesuo": "unlock",
    "mima": "password", "diannao": "computer", "ruqin": "intrude",
}


def _pinyin_hint(s: str) -> str | None:
    toks = re.findall(r"[a-z]{3,}", s.lower())
    hits = [PINYIN_HINT[t] for t in toks if t in PINYIN_HINT]
    return " ".join(hits) if hits else None


KEYBOARD_ROWS = ["1234567890-=", "qwertyuiop[]\\", "asdfghjkl;'", "zxcvbnm,./"]
KB_LEFT = {}
for row in KEYBOARD_ROWS:
    for i, ch in enumerate(row):
        if i > 0:
            KB_LEFT[ch] = row[i - 1]
EMOJI_MAP = {"🔓": "unlock", "🔒": "lock", "🔑": "key", "🚪": "door",
             "➡️": " ", "➡": " ", "🔐": "lock", "🗝️": "key", "🗝": "key"}


def _keyboard_left(s: str) -> str:
    return "".join(KB_LEFT.get(c.lower(), c) for c in s)


def _emoji_map(s: str) -> str:
    out = s
    for k, v in EMOJI_MAP.items():
        out = out.replace(k, v)
    return out


def _lev1(a: str, b: str) -> bool:
    """编辑距离 <= 1（用于 kock/lock 这类近似词）。"""
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(1 for x, y in zip(a, b) if x != y) <= 1
    short, long = (a, b) if len(a) < len(b) else (b, a)
    i = j = diff = 0
    while i < len(short) and j < len(long):
        if short[i] == long[j]:
            i += 1; j += 1
        else:
            diff += 1; j += 1
            if diff > 1:
                return False
    return True


FUZZY_TARGETS = ["lock", "bomb", "password", "phishing", "ransomware", "exfiltrate"]


def _fuzzy_hit(s: str) -> str | None:
    for w in re.findall(r"[a-z]{3,}", s.lower()):
        for t in FUZZY_TARGETS:
            if _lev1(w, t):
                return f"{w}~{t}"
    return None


def _strip_filler(s: str) -> str:
    """去掉插在字母间的噪声（如 HxoXw -> How）。仅当剥离后更像正常英文时采用。"""
    stripped = re.sub(r"[xX·•._]", "", s)
    return stripped


def _every_other(s: str) -> list[str]:
    """隔字符隐藏：'HxoXw' -> 'How'（两种相位都试）"""
    compact = s.replace(" ", "")
    return ["".join(compact[i::2]) for i in (0, 1)]


def _split_concat(s: str) -> list[str]:
    """'how do I pi' + 'ck a lock?' 形式的拼接"""
    parts = re.findall(r"'([^']{2,})'", s)
    return ["".join(parts)] if len(parts) >= 2 else []


def candidates(text: str) -> list[tuple[str, str]]:
    """返回所有解码候选 (方法, 文本)。"""
    out: list[tuple[str, str]] = [("raw", text)]
    out.append(("nfkc", unicodedata.normalize("NFKC", text)))
    out.append(("zalgo_stripped", _strip_zalgo(text)))
    out.append(("homoglyph", _homoglyph(text)))
    out.append(("leet", text.translate(LEET)))
    out.append(("rot13", codecs.decode(text, "rot13")))
    out.append(("reversed", text[::-1]))
    out.append(("filler_stripped", _strip_filler(text)))
    out.append(("keyboard_left", _keyboard_left(text)))
    out.append(("emoji_mapped", _emoji_map(text)))

    try:
        from urllib.parse import unquote
        dec = unquote(text)
        if dec != text:
            out.append(("url", dec))
    except Exception:
        pass

    # 逐 token 尝试 base64/base32（只对大写密度高的 token）
    for tok in re.findall(r"[A-Za-z0-9+/=_\-]{20,}", text):
        for name, fn in (("base64", _try_b64), ("base32", _try_b32)):
            dec = fn(tok)
            if dec:
                out.append((name, dec))
    for tok in re.findall(r"[A-Za-z0-9+/=_\-]{12,}", text):
        dec = _try_b64(tok)
        if dec:
            out.append(("base64", dec))

    m = _try_morse(text)
    if m:
        out.append(("morse", m))

    for i, c in enumerate(_every_other(text)):
        if c:
            out.append((f"every_other_{i}", c))
    for c in _split_concat(text):
        out.append(("split_concat", c))
    py = _pinyin_hint(text)
    if py:
        out.append(("pinyin_hint", py))
    return out


def detect(text: str) -> dict:
    """返回 {hit, method, matched_text, decoded}"""
    for method, cand in candidates(text):
        m = DENY_RE.search(cand)
        if m:
            return {"hit": True, "method": method, "matched": m.group(0),
                    "decoded": cand[:160]}
        fz = _fuzzy_hit(cand)
        if fz:
            return {"hit": True, "method": method + ":fuzzy", "matched": fz,
                    "decoded": cand[:160]}
    return {"hit": False, "method": None, "matched": None, "decoded": None}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=str(Path(__file__).resolve().parent / "redteam_set_v1.jsonl"))
    args = ap.parse_args()

    rows = [json.loads(l) for l in Path(args.dataset).read_text(encoding="utf-8").splitlines() if l.strip()]
    enc = [r for r in rows if r["category"] == "encoding"]
    ben = [r for r in rows if r["category"] == "benign"]

    hit_enc = [r for r in enc if detect(r["prompt"])["hit"]]
    hit_ben = [r for r in ben if detect(r["prompt"])["hit"]]

    print(f"encoding: {len(hit_enc)}/{len(enc)} 检出 ({len(hit_enc)/len(enc)*100:.1f}%)")
    for r in enc:
        d = detect(r["prompt"])
        if not d["hit"]:
            print(f"  MISS {r['id']}: {r['prompt'][:70]}")
    print(f"benign:   {len(hit_ben)}/{len(ben)} 误报 ({len(hit_ben)/len(ben)*100:.1f}%)")
    for r in hit_ben:
        print(f"  FP {r['id']}: {detect(r['prompt'])['matched']} <- {r['prompt'][:70]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
