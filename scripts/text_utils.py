"""
text_utils.py
-------------
Minimal Arabic text normalization used before embedding/indexing.

This is intentionally light — orthographic normalization only, NOT
stemming/lemmatization (that would be a bigger NLP dependency and is exactly
the kind of "unnecessary technology" the assignment says to avoid). It fixes
trivial mismatches like أ/إ/آ vs ا, ة vs ه, ى vs ي, and stray diacritics /
tatweel, which are extremely common in Arabic web/UI text and otherwise
silently hurt TF-IDF token overlap.

It will NOT fix morphological mismatches (e.g. singular/plural: سنة vs
سنوات) — that limitation is deliberately left visible and is called out in
`evaluation.py` / the final report as a real, demonstrated Query Mismatch
finding for the Diagnosis/Optimization agents to pick up later, rather than
being quietly patched over here.
"""

from __future__ import annotations

import re

_DIACRITICS = re.compile(r"[\u0610-\u061A\u064B-\u065F\u06D6-\u06DC\u06DF-\u06E8\u06EA-\u06ED]")
_TATWEEL = re.compile(r"\u0640")


def normalize_arabic(text: str) -> str:
    if not text:
        return text
    text = _DIACRITICS.sub("", text)
    text = _TATWEEL.sub("", text)
    text = re.sub(r"[إأآا]", "ا", text)
    text = text.replace("ى", "ي")
    text = text.replace("ة", "ه")
    text = re.sub(r"\s+", " ", text).strip()
    return text
