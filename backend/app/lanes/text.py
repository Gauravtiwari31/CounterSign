"""Canonical text, sentence split with offsets, and quote -> span location.

All offsets are character offsets into the canonical text of a version.
The LLM never supplies offsets: it only quotes text, and `locate` finds it.
"""
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

from rapidfuzz import fuzz

_TRANS = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'",
    "“": '"', "”": '"', "„": '"', "″": '"',
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "―": "-", "−": "-",
    " ": " ", " ": " ", " ": " ", "…": "...",
}


def canonical(text: str) -> str:
    return unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))


def normalise_with_map(text: str) -> tuple[str, list[int]]:
    """Fold quotes/dashes/case and collapse whitespace; index_map[i] is the source offset of output char i."""
    out: list[str] = []
    index_map: list[int] = []
    prev_space = False
    for i, ch in enumerate(text):
        for c in _TRANS.get(ch, ch):
            if c.isspace():
                if prev_space:
                    continue
                c, prev_space = " ", True
            else:
                prev_space = False
            for cc in c.lower():
                out.append(cc)
                index_map.append(i)
    return "".join(out), index_map


def normalise(text: str) -> str:
    return normalise_with_map(text)[0].strip()


@dataclass(frozen=True)
class Sentence:
    id: int
    start: int
    end: int
    text: str


@lru_cache(maxsize=1)
def _nlp():
    import spacy

    nlp = spacy.blank("en")
    nlp.add_pipe("sentencizer")
    return nlp


def split_sentences(text: str) -> list[Sentence]:
    """spaCy sentencizer, plus hard breaks at newlines (captions are line-oriented)."""
    sentences: list[Sentence] = []
    pos = 0
    for line in text.split("\n"):
        if line.strip():
            for sent in _nlp()(line).sents:
                raw = sent.text
                lead = len(raw) - len(raw.lstrip())
                body = raw.strip()
                if body:
                    start = pos + sent.start_char + lead
                    sentences.append(Sentence(len(sentences), start, start + len(body), body))
        pos += len(line) + 1
    return sentences


def sentence_for(sentences: list[Sentence], start: int, end: int) -> Sentence | None:
    for s in sentences:
        if s.start <= start < s.end or (s.start < end <= s.end):
            return s
    return None


def _norm_bounds(index_map: list[int], lo: int, hi: int) -> tuple[int, int]:
    a = next((k for k, src in enumerate(index_map) if src >= lo), len(index_map))
    b = next((k for k, src in enumerate(index_map) if src >= hi), len(index_map))
    return a, b


def locate(quote: str, text: str, hint: tuple[int, int] | None = None) -> tuple[int, int] | None:
    """Find `quote` in `text`, preferring the hint range. Returns (start, end) or None (caller drops the finding)."""
    if not quote or len(quote.strip()) < 2:
        return None
    q = quote.strip()
    lo, hi = hint if hint else (0, len(text))

    # 1. exact, inside the hint first
    idx = text.find(q, lo, hi)
    if idx < 0 and hint:
        idx = text.find(q)
    if idx >= 0:
        return idx, idx + len(q)

    # 2. normalised match mapped back to source offsets
    nt, m = normalise_with_map(text)
    nq = normalise(q)
    if not nq:
        return None
    a, b = _norm_bounds(m, lo, hi)
    k = nt.find(nq, a, b)
    if k < 0 and hint:
        k = nt.find(nq)
    if k >= 0:
        return m[k], m[k + len(nq) - 1] + 1

    # 3. fuzzy (>= 95) within the hint sentence only; numbers must match exactly
    window = nt[a:b]
    if hint and len(nq) >= 8 and window:
        al = fuzz.partial_ratio_alignment(nq, window)
        if al and al.score >= 95 and al.dest_end > al.dest_start:
            start, end = m[a + al.dest_start], m[a + al.dest_end - 1] + 1
            while start > lo and text[start - 1].isalnum():
                start -= 1
            while end < hi and text[end].isalnum():
                end += 1
            if _digits(text[start:end]) == _digits(q):
                return start, end
    return None


def _digits(s: str) -> list[str]:
    return re.findall(r"\d+", s)


def contains_normalised(needle: str, haystack: str) -> bool:
    n = normalise(needle)
    return bool(n) and n in normalise(haystack)
