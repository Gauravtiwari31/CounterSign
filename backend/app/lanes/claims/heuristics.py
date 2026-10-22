"""Deterministic fallback when both LLM providers fail. The claims lane never silently passes.

Claims are flagged per clause (not per sentence) so a reviewer sees exactly which words need evidence.
"""
import re

from app.lanes.text import Sentence
from app.lanes.types import Claim

PATTERNS: list[tuple[str, re.Pattern]] = [
    ("environmental", re.compile(r"\b(100%\s*natural|all[- ]natural|natural|eco[- ]?friendly|sustainabl\w*|biodegradable|"
                                 r"recycl\w*|compostable|carbon[- ]neutral|plastic[- ]free|green(er)?|organic|"
                                 r"chemical[- ]free|vegan|cruelty[- ]free)\b", re.I)),
    ("health_benefit", re.compile(r"\b(clinically|proven|dermatologist\w*|cures?|heals?|clears?|treats?|prevents?|"
                                  r"boosts? immunity|anti[- ]?\w+|guaranteed?|risk[- ]free|works for every)\b", re.I)),
    ("free_offer", re.compile(r"(?<![\w-])free\b(?![- ]from)", re.I)),
    ("comparative", re.compile(r"\b(best|no\.?\s?1|#1|number one|better than|cheaper than|less \w+ than|more \w+ than|"
                               r"fastest|leading|most \w+|only \w+ that|unlike)\b", re.I)),
    ("price_offer", re.compile(r"(₹\s?\d|rs\.?\s?\d|\d+\s?%\s?off|discount|\bsale\b|cashback|\boffer\b|costs?\b|priced)", re.I)),
    ("certification_award", re.compile(r"\b(certified|award\w*|approved|registered|recommended by|accredited|rated|"
                                       r"tested|licensed|free from)\b", re.I)),
    ("numeric", re.compile(r"\d")),
]
CLAUSE_BREAK = re.compile(r",\s+|;\s+|:\s+|\s+(?:and|but|while|so)\s+", re.I)
FALLBACK_NOTE = "AI check unavailable: flagged by pattern, needs human review."


def _clauses(s: Sentence) -> list[tuple[int, int]]:
    spans, pos = [], 0
    for m in CLAUSE_BREAK.finditer(s.text):
        spans.append((pos, m.start()))
        pos = m.end()
    spans.append((pos, len(s.text)))
    return [(s.start + a, s.start + b) for a, b in spans if s.text[a:b].strip(" .!?")]


def detect(sentences: list[Sentence]) -> list[Claim]:
    claims = []
    for s in sentences:
        for start, end in _clauses(s):
            clause = s.text[start - s.start:end - s.start]
            stripped = clause.rstrip(" .!?")
            end = start + len(stripped)
            for claim_type, pat in PATTERNS:
                if pat.search(stripped):
                    claims.append(Claim(sentence_id=s.id, start=start, end=end, quote=stripped,
                                        claim_type=claim_type, atomic=s.text))
                    break
    return claims
