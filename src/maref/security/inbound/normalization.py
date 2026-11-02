"""Inbound 归一化引擎 — 编码攻击的多路还原 (Lexsi D6 实证沉淀)。

背景 (2026-11-02 实测): 在 CohereLabs/tiny-aya-global 上做 refusal-direction
alpha sweep, encoding 类攻击 6 档 alpha 的 ASR 始终 95.8%-100%; probe 确认
steering 的输出确有变化, 但对编码输入无效 — 因为安全拒绝作用于**语义层**,
base64/rot13/分片后的输入在模型内部不构成"有害请求"。

因此编码攻击必须在**输入侧**还原。本模块只做还原, 不做裁决 (裁决在
``gate.py``), 这样解码逻辑可独立测试与复用。

支持: base64 / base32 / rot13 / url / 反转 / 分片拼接 / 隔字符 / 填充剥离 /
leet / 同形字 / zalgo / morse / 键盘左移 / emoji 替换 / 拼音提示。
"""

from __future__ import annotations

import base64
import binascii
import codecs
import re
import unicodedata
from dataclasses import dataclass

MAX_INPUT_CHARS = 100_000
MAX_CANDIDATES = 16


@dataclass(frozen=True, slots=True)
class DecodedCandidate:
    """一路解码结果。``method`` 为 ``"raw"`` 表示原文。"""

    method: str
    text: str

    def __str__(self) -> str:  # pragma: no cover - 调试便利
        return f"{self.method}:{self.text[:40]}"


_HOMOGLYPH = {
    "а": "a",
    "е": "e",
    "о": "o",
    "р": "p",
    "с": "c",
    "х": "x",
    "у": "y",
    "і": "i",
    "ј": "j",
    "ѕ": "s",
    "ԁ": "d",
    "һ": "h",
    "ӏ": "l",
    "ո": "n",
    "Α": "A",
    "Β": "B",
    "Ε": "E",
    "Ζ": "Z",
    "Η": "H",
    "Ι": "I",
    "Κ": "K",
    "Μ": "M",
    "Ν": "N",
    "Ο": "O",
    "Ρ": "P",
    "Τ": "T",
    "Υ": "Y",
    "Χ": "X",
    "ο": "o",
    "ι": "i",
    "κ": "k",
    "ν": "v",
    "ρ": "p",
    "τ": "t",
    "υ": "u",
}
_LEET = str.maketrans(
    {"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"}
)
_MORSE = {
    ".-": "a",
    "-...": "b",
    "-.-.": "c",
    "-..": "d",
    ".": "e",
    "..-.": "f",
    "--.": "g",
    "....": "h",
    "..": "i",
    ".---": "j",
    "-.-": "k",
    ".-..": "l",
    "--": "m",
    "-.": "n",
    "---": "o",
    ".--.": "p",
    "--.-": "q",
    ".-.": "r",
    "...": "s",
    "-": "t",
    "..-": "u",
    "...-": "v",
    ".--": "w",
    "-..-": "x",
    "-.--": "y",
    "--..": "z",
    "..--..": "?",
    "----.": "9",
    "-----": "0",
}
_KEYBOARD_ROWS = ["1234567890-=", "qwertyuiop[]\\", "asdfghjkl;'", "zxcvbnm,./"]
_KB_LEFT: dict[str, str] = {}
for _row in _KEYBOARD_ROWS:
    for _i, _ch in enumerate(_row):
        if _i > 0:
            _KB_LEFT[_ch] = _row[_i - 1]
del _row, _i, _ch

_EMOJI_MAP = {
    "🔓": "unlock",
    "🔒": "lock",
    "🔑": "key",
    "🚪": "door",
    "➡️": " ",
    "➡": " ",
    "🔐": "lock",
    "🗝️": "key",
    "🗝": "key",
}
_PINYIN_HINT = {
    "ruhe": "how",
    "dakai": "open",
    "suo": "lock",
    "jiesuo": "unlock",
    "mima": "password",
    "diannao": "computer",
    "ruqin": "intrude",
}


_COMMON_WORDS = frozenset(
    {
        "the",
        "and",
        "how",
        "do",
        "does",
        "i",
        "a",
        "an",
        "to",
        "is",
        "of",
        "in",
        "for",
        "you",
        "your",
        "all",
        "my",
        "what",
        "can",
        "with",
        "on",
        "are",
        "this",
        "that",
        "it",
        "me",
        "we",
        "they",
        "he",
        "she",
        "not",
        "no",
        "yes",
        "explain",
        "tell",
        "write",
        "give",
        "please",
        "ignore",
        "previous",
        "instructions",
        "method",
        "answer",
        "question",
    }
)


def _common_word_hits(s: str) -> int:
    toks = re.findall(r"[a-z]{2,}", s.lower())
    return sum(1 for t in toks if t in _COMMON_WORDS)


def _vowel_ratio(s: str) -> float:
    letters = [c for c in s.lower() if c.isalpha()]
    if len(letters) < 6:
        return 0.0
    return sum(1 for c in letters if c in "aeiou") / len(letters)


def _looks_english(s: str) -> bool:
    return bool(s.strip()) and 0.18 <= _vowel_ratio(s) <= 0.58 and _common_word_hits(s) >= 1


def _strip_zalgo(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _homoglyph(s: str) -> str:
    return "".join(_HOMOGLYPH.get(c, c) for c in s)


def _strip_filler(s: str) -> str:
    """去掉插在字母间的噪声 (HxoXw -> How)。"""
    return re.sub(r"[xX·•._]", "", s)


def _keyboard_left(s: str) -> str:
    return "".join(_KB_LEFT.get(c.lower(), c) for c in s)


def _emoji_map(s: str) -> str:
    out = s
    for k, v in _EMOJI_MAP.items():
        out = out.replace(k, v)
    return out


def _try_b64(token: str) -> str | None:
    t = token.strip().strip("\"'")
    if len(t) < 12:
        return None
    if not re.fullmatch(r"[A-Za-z0-9+/=_-]+", t):
        return None
    for pad in range(4):
        try:
            raw = base64.b64decode(t + "=" * pad, validate=False)
        except (binascii.Error, ValueError):
            continue
        out = raw.decode("utf-8", "ignore")
        if out.strip() and sum(c.isprintable() for c in out) >= len(out) * 0.8:
            return out
    return None


def _try_b32(token: str) -> str | None:
    t = re.sub(r"[^A-Z2-7]", "", token.upper())
    if len(t) < 12:
        return None
    for pad in range(8):
        try:
            out = base64.b32decode(t + "=" * pad).decode("utf-8", "ignore")
        except (binascii.Error, ValueError):
            continue
        if out.strip() and sum(c.isprintable() for c in out) >= len(out) * 0.8:
            return out
    return None


def _try_morse(s: str) -> str | None:
    frag = max(re.findall(r"[.\-/\s]{9,}", s), key=len, default="")
    if not frag.strip():
        return None
    words = []
    for word in frag.strip().split("/"):
        letters = [_MORSE.get(code, "") for code in word.split()]
        words.append("".join(letters))
    out = " ".join(w for w in words if w)
    return out or None


def _every_other(s: str) -> list[str]:
    compact = s.replace(" ", "")
    return ["".join(compact[i::2]) for i in (0, 1)]


def _split_concat(s: str) -> list[str]:
    parts = re.findall(r"'([^']{2,})'", s)
    return ["".join(parts)] if len(parts) >= 2 else []


def _pinyin_hint(s: str) -> str | None:
    toks = re.findall(r"[a-z]{3,}", s.lower())
    hits = [_PINYIN_HINT[t] for t in toks if t in _PINYIN_HINT]
    return " ".join(hits) if hits else None


def decode_candidates(
    text: str, *, max_candidates: int = MAX_CANDIDATES
) -> tuple[DecodedCandidate, ...]:
    """返回原文 + 所有解码候选 (去重, 按方法顺序)。

    超过 ``MAX_INPUT_CHARS`` 的输入直接抛 ``ValueError`` (防解码 DoS)。
    """
    if not isinstance(text, str):
        raise TypeError("text must be str")
    if len(text) > MAX_INPUT_CHARS:
        raise ValueError(f"input too long: {len(text)} > {MAX_INPUT_CHARS}")

    out: list[DecodedCandidate] = [DecodedCandidate("raw", text)]
    seen = {text}

    def add(method: str, value: str | None) -> None:
        if not value or value in seen or len(value.strip()) < 3:
            return
        seen.add(value)
        out.append(DecodedCandidate(method, value))

    add("nfkc", unicodedata.normalize("NFKC", text))
    add("zalgo_stripped", _strip_zalgo(text))
    add("homoglyph", _homoglyph(text))
    # leet 只在原文确有数字/符号时才有意义, 否则会产生噪声候选
    if re.search(r"[0-9@$]", text):
        add("leet", text.translate(_LEET))
    # rot13 / 键盘左移: 仅当还原结果像英文时采用 (否则任意文本都会产生候选)
    rot = codecs.decode(text, "rot13")
    if _looks_english(rot):
        add("rot13", rot)
    rev = text[::-1]
    if _looks_english(rev):
        add("reversed", rev)
    fill = _strip_filler(text)
    if len(text) - len(fill) >= 3 and _looks_english(fill):
        add("filler_stripped", fill)
    kb = _keyboard_left(text)
    if _looks_english(kb):
        add("keyboard_left", kb)
    add("emoji_mapped", _emoji_map(text))

    try:
        from urllib.parse import unquote

        add("url", unquote(text))
    except Exception:  # pragma: no cover - 极端输入
        pass

    for tok in re.findall(r"[A-Za-z0-9+/=_-]{12,}", text):
        add("base64", _try_b64(tok))
        add("base32", _try_b32(tok))
        if len(out) >= max_candidates:
            break

    add("morse", _try_morse(text))
    for idx, cand in enumerate(_every_other(text)):
        if _looks_english(cand):
            add(f"every_other_{idx}", cand)
    for cand in _split_concat(text):
        add("split_concat", cand)
    add("pinyin_hint", _pinyin_hint(text))

    return tuple(out[:max_candidates])


__all__ = ["DecodedCandidate", "decode_candidates", "MAX_INPUT_CHARS", "MAX_CANDIDATES"]
