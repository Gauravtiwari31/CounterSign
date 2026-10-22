"""PII masking before any LLM call: Presidio (spaCy en_core_web_sm) + Indian regex recognisers.

Masking is reversible per job: <PERSON_1> -> original. Rulebook terms, product names and fact entities are on
an allow-list so "AloeCalm" is never masked as a PERSON and claim matching keeps working.
"""
import logging
import re
from functools import lru_cache

from app.config import get_settings

log = logging.getLogger("countersign.pii")

REGEX_RECOGNISERS: list[tuple[str, re.Pattern]] = [
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("PHONE", re.compile(r"(?<!\d)(?:\+91[\-\s]?)?[6-9]\d{4}[\-\s]?\d{5}(?!\d)")),
    ("AADHAAR", re.compile(r"(?<!\d)\d{4}[\s-]?\d{4}[\s-]?\d{4}(?!\d)")),
    ("PAN", re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")),
]
PRESIDIO_ENTITIES = ["PERSON", "PHONE_NUMBER", "EMAIL_ADDRESS", "CREDIT_CARD", "IBAN_CODE", "IP_ADDRESS"]
_PRESIDIO_LABEL = {"PHONE_NUMBER": "PHONE", "EMAIL_ADDRESS": "EMAIL"}


@lru_cache(maxsize=1)
def _presidio():
    mode = get_settings().pii_engine
    if mode == "regex":
        return None
    try:
        from presidio_analyzer import AnalyzerEngine
        from presidio_analyzer.nlp_engine import NlpEngineProvider

        provider = NlpEngineProvider(nlp_configuration={
            "nlp_engine_name": "spacy", "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
        })
        return AnalyzerEngine(nlp_engine=provider.create_engine(), supported_languages=["en"])
    except Exception as e:  # missing package or model
        if mode == "presidio":
            raise
        log.warning("Presidio unavailable (%s); using regex-only PII masking", e)
        return None


def engine_name() -> str:
    return "presidio+regex (en_core_web_sm)" if _presidio() else "regex"


class Masker:
    def __init__(self, allow_terms: set[str] | None = None):
        self.allow = {t.lower() for t in (allow_terms or set()) if t}
        self.forward: dict[str, str] = {}
        self.reverse: dict[str, str] = {}
        self._counts: dict[str, int] = {}

    def _allowed(self, value: str) -> bool:
        v = value.lower().strip()
        return any(v == a or v in a or a in v for a in self.allow)

    def _placeholder(self, label: str, value: str) -> str:
        if value in self.forward:
            return self.forward[value]
        self._counts[label] = self._counts.get(label, 0) + 1
        ph = f"<{label}_{self._counts[label]}>"
        self.forward[value] = ph
        self.reverse[ph] = value
        return ph

    def _spans(self, text: str) -> list[tuple[int, int, str]]:
        spans = [(m.start(), m.end(), label) for label, pat in REGEX_RECOGNISERS for m in pat.finditer(text)]
        analyzer = _presidio()
        if analyzer is not None:
            for r in analyzer.analyze(text=text, language="en", entities=PRESIDIO_ENTITIES, score_threshold=0.5):
                spans.append((r.start, r.end, _PRESIDIO_LABEL.get(r.entity_type, r.entity_type)))
        spans = [s for s in spans if not self._allowed(text[s[0]:s[1]])]
        spans.sort(key=lambda s: (s[0], -(s[1] - s[0])))
        merged: list[tuple[int, int, str]] = []
        for s in spans:
            if merged and s[0] < merged[-1][1]:
                continue
            merged.append(s)
        return merged

    def mask(self, text: str) -> str:
        out, pos = [], 0
        for start, end, label in self._spans(text):
            out.append(text[pos:start])
            out.append(self._placeholder(label, text[start:end]))
            pos = end
        out.append(text[pos:])
        return "".join(out)

    def unmask(self, text: str | None) -> str | None:
        if not text:
            return text
        for ph, value in self.reverse.items():
            text = text.replace(ph, value)
        return text
