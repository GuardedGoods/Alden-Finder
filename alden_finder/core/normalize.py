"""Title + description classifier.

Given a retailer product title (and optional body_html / variant strings),
extract the canonical Alden fields: last, leather, color, category,
model number, US size, width.

The matchers are regex + alias tables loaded from the data/ YAMLs. Ambiguity
is resolved with a simple priority: shell-cordovan color names imply
leather=Shell Cordovan, etc.
"""

from __future__ import annotations

import functools
import re
from pathlib import Path

import yaml

from alden_finder.core.models import Category

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


@functools.lru_cache(maxsize=1)
def _load_yaml(name: str) -> list[dict]:
    return yaml.safe_load((DATA_DIR / name).read_text()) or []


# ---------------------------------------------------------------------------
# Primitive matchers
# ---------------------------------------------------------------------------


def _contains_alias(text: str, aliases: list[str]) -> str | None:
    """Return the matched alias or None. Matches at token boundaries, case-insensitive."""
    t = text.lower()
    # Prefer the longest alias that matches.
    for alias in sorted(aliases, key=len, reverse=True):
        a = alias.lower()
        pattern = r"(?<![\w-])" + re.escape(a) + r"(?![\w-])"
        if re.search(pattern, t):
            return alias
    return None


def detect_last(text: str, model_number: str | None = None) -> str | None:
    for entry in _load_yaml("lasts.yaml"):
        if _contains_alias(text, entry["aliases"]):
            return entry["name"]
    if model_number:
        for entry in _load_yaml("lasts.yaml"):
            if model_number in (entry.get("models") or []):
                return entry["name"]
    return None


def detect_color(text: str) -> tuple[str | None, str | None]:
    """Returns (color_name, leather_hint)."""
    for entry in _load_yaml("colors.yaml"):
        if _contains_alias(text, entry["aliases"]):
            return entry["name"], entry.get("leather_hint")
    return None, None


def detect_leather(text: str, color_hint: str | None = None) -> str | None:
    for entry in _load_yaml("leathers.yaml"):
        if _contains_alias(text, entry["aliases"]):
            return entry["name"]
    return color_hint


_CATEGORY_PATTERNS: list[tuple[Category, list[str]]] = [
    (Category.INDY, [r"\bindy\b", r"\b405\b"]),
    (Category.CHUKKA, [r"\bchukka\b", r"\b1339\b", r"\b1340\b"]),
    (Category.LWB, [r"\blong\s*wing\b", r"\blwb\b", r"\b975\b", r"\b97[56]4\b"]),
    (Category.BOOT, [r"\bboot\b", r"\btanker\b"]),
    (Category.TASSEL, [r"\btassel\b", r"\b56[3-6][0-9]\b"]),
    (Category.LOAFER, [r"\bloafer\b", r"\blhs\b", r"\bpenny\b", r"\bfull\s*strap\b"]),
    (Category.BLUCHER, [r"\bblucher\b", r"\bplain\s*toe\b", r"\bpt\b", r"\bptb\b", r"\b990\b"]),
    (Category.OXFORD, [r"\boxford\b", r"\bbalmoral\b", r"\bcap\s*toe\b"]),
    (Category.SADDLE, [r"\bsaddle\b"]),
    (Category.SLIPPER, [r"\bslipper\b", r"\bvelvet\b"]),
]


def detect_category(text: str) -> Category:
    t = text.lower()
    for cat, patterns in _CATEGORY_PATTERNS:
        for p in patterns:
            if re.search(p, t):
                return cat
    return Category.OTHER


_MODEL_NUMBER = re.compile(
    r"(?:(?<=\s)|^)(?:no\.?\s*)?([0-9]{2,4}[A-Z]?|[A-Z]\d{3,5}[A-Z]?)(?=[\s,.;:/\-]|$)"
)


def detect_model_number(text: str) -> str | None:
    for m in _MODEL_NUMBER.finditer(text):
        candidate = m.group(1)
        # Filter obvious non-models: 4-digit years, stock counts, etc.
        if candidate.isdigit() and len(candidate) == 4 and 1900 <= int(candidate) <= 2100:
            continue
        return candidate
    return None


# Width is typically rendered as "10D", "10 D", "10.5 / D", or "Size 10 D".
# We match a width letter adjacent to a size number, OR a width token preceded
# by "width" / "US" / "size", to avoid catching the "D" in "Dainite" etc.
_WIDTH_RE = re.compile(
    r"(?:\b\d{1,2}(?:[.,]\d)?\s*/?\s*|\b(?:width|us|size)\s+)(AA|A|B|C|D|E|EE|EEE|EEEE)\b",
    re.IGNORECASE,
)


def detect_width(text: str) -> str | None:
    m = _WIDTH_RE.search(text.upper())
    return m.group(1) if m else None


_SIZE_RE = re.compile(
    r"(?:(?:size|us)\s*)?\b([4-9](?:\.5)?|1[0-6](?:\.5)?)\s*(?:us|d|e|ee|eee|b|c)?\b",
    re.IGNORECASE,
)


def detect_size_us(text: str) -> float | None:
    m = _SIZE_RE.search(text)
    if not m:
        return None
    try:
        size = float(m.group(1))
    except ValueError:
        return None
    if 4 <= size <= 16:
        return size
    return None


# ---------------------------------------------------------------------------
# Composite
# ---------------------------------------------------------------------------


def classify(title: str, body: str = "", variant: str = "") -> dict:
    """Return a dict of canonical fields extracted from the text."""
    haystack = " ".join(x for x in (title, body, variant) if x)
    color, color_leather_hint = detect_color(haystack)
    leather = detect_leather(haystack, color_hint=color_leather_hint)
    model_number = detect_model_number(title) or detect_model_number(haystack)
    return {
        "last_name": detect_last(haystack, model_number),
        "leather_name": leather,
        "color": color,
        "category": detect_category(haystack).value,
        "model_number": model_number,
        "size_us": detect_size_us(variant or haystack),
        "width": detect_width(variant or haystack),
    }
