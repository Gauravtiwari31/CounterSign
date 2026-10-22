"""Deterministic rules lane. No AI. Target: <50 ms for a 300-word draft."""
import re
from collections.abc import Callable
from dataclasses import dataclass, field

import textstat

from app.lanes.text import split_sentences


@dataclass
class RuleSpec:
    code: str
    type: str
    params: dict
    severity: str = "warning"
    channels: list[str] | None = None
    title: str = ""
    description: str = ""
    id: str | None = None


@dataclass
class RuleHit:
    code: str
    rule_id: str | None
    severity: str
    start: int
    end: int
    span_text: str
    message: str
    explanation: str
    replacement: str | None = None  # deterministic fix for the span
    ai_fixable: bool = False  # no deterministic fix, but an AI rewrite is allowed
    extra: dict = field(default_factory=dict)


# ---------- helpers ----------

_URLISH = re.compile(
    r"(https?://\S+|www\.\S+|\S+@\S+\.\S+|[#@][\w-]+"
    r"|\b[\w-]+(?:\.[\w-]+)*\.(?:com|in|co|org|net|io|app|shop|store)\b(?:/\S*)?)", re.IGNORECASE)
_QUOTED = re.compile(r'"[^"\n]*"|“[^”\n]*”')


def _excluded_ranges(text: str) -> list[tuple[int, int]]:
    return [m.span() for m in _URLISH.finditer(text)]


def _inside(ranges: list[tuple[int, int]], start: int, end: int) -> bool:
    return any(a <= start and end <= b for a, b in ranges)


def _phrase_pattern(phrase: str) -> re.Pattern:
    body = r"[\s\-]*".join(re.escape(p) for p in re.split(r"[\s\-]+", phrase.strip()) if p)
    left = r"(?<!\w)" if phrase[:1].isalnum() else ""
    right = r"(?!\w)" if phrase[-1:].isalnum() else ""
    return re.compile(left + body + right, re.IGNORECASE)


def _last_sentence(text: str) -> tuple[int, int] | None:
    sents = split_sentences(text)
    if not sents:
        return None
    return sents[-1].start, sents[-1].end


def _append_hit(rule: RuleSpec, text: str, addition: str, message: str, explanation: str) -> RuleHit | None:
    span = _last_sentence(text)
    if span is None:
        return None
    s, e = span
    tail = text[s:e]
    sep = "" if tail.endswith((" ", "\n")) else " "
    return RuleHit(rule.code, rule.id, rule.severity, s, e, tail, message, explanation, replacement=tail + sep + addition)


def _camel_parts(word: str) -> list[str]:
    return re.findall(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])", word) or [word]


# ---------- rule types ----------

def check_terminology(rule: RuleSpec, text: str, channel: str) -> list[RuleHit]:
    preferred: str = rule.params["preferred"]
    forbidden: list[str] = rule.params.get("forbidden", [])
    patterns = [_phrase_pattern(f) for f in forbidden]
    if rule.params.get("auto_variants", True):
        parts = _camel_parts(preferred)
        patterns.append(re.compile(r"(?<!\w)" + r"[\s\-]?".join(re.escape(p) for p in parts) + r"(?!\w)", re.IGNORECASE))
    excluded = _excluded_ranges(text)
    hits: dict[tuple[int, int], RuleHit] = {}
    for pat in patterns:
        for m in pat.finditer(text):
            if m.group(0) == preferred or _inside(excluded, *m.span()):
                continue
            hits.setdefault(m.span(), RuleHit(
                rule.code, rule.id, rule.severity, m.start(), m.end(), m.group(0),
                f'Use "{preferred}", not "{m.group(0)}"',
                rule.description or f"The approved product name is {preferred}.",
                replacement=preferred,
            ))
    return list(hits.values())


def check_banned_phrase(rule: RuleSpec, text: str, channel: str) -> list[RuleHit]:
    alt = rule.params.get("alternative")
    hits = []
    for phrase in rule.params.get("phrases", []):
        for m in _phrase_pattern(phrase).finditer(text):
            hits.append(RuleHit(
                rule.code, rule.id, rule.severity, m.start(), m.end(), m.group(0),
                f'Banned phrase: "{m.group(0)}"',
                rule.description or "This phrase is not allowed in brand copy.",
                replacement=alt, ai_fixable=alt is None,
            ))
    return hits


def check_required_phrase(rule: RuleSpec, text: str, channel: str) -> list[RuleHit]:
    phrase: str = rule.params["text"]
    trigger = rule.params.get("trigger")
    if trigger:
        tm = re.search(trigger, text, re.IGNORECASE)
        if not tm:
            return []
    position = rule.params.get("position", "any")
    if position == "end":
        span = _last_sentence(text)
        region = text[span[0]:] if span else text
    else:
        region = text
    if _phrase_pattern(phrase).search(region):
        return []
    why = f' because the draft mentions "{tm.group(0)}"' if trigger else ""
    hit = _append_hit(rule, text, phrase, f'Missing required text: "{phrase}"',
                      (rule.description or f'"{phrase}" is required') + why + ".")
    return [hit] if hit else []


def check_punctuation_limit(rule: RuleSpec, text: str, channel: str) -> list[RuleHit]:
    ch: str = rule.params.get("char", "!")
    max_per_draft: int = rule.params.get("max_per_draft", 1)
    max_run: int = rule.params.get("max_run", 1)
    quoted = [m.span() for m in _QUOTED.finditer(text)]
    hits, kept = [], 0
    for m in re.finditer(re.escape(ch) + "+", text):
        if _inside(quoted, *m.span()):
            continue
        run = m.group(0)
        if kept < max_per_draft:
            kept += 1
            if len(run) > max_run:
                hits.append(RuleHit(
                    rule.code, rule.id, rule.severity, m.start(), m.end(), run,
                    f'Repeated "{ch}" ({len(run)} in a row)',
                    rule.description or f'No more than {max_run} "{ch}" in a row.',
                    replacement=ch * max_run,
                ))
        else:
            hits.append(RuleHit(
                rule.code, rule.id, rule.severity, m.start(), m.end(), run,
                f'Too many "{ch}" (limit {max_per_draft} per draft)',
                rule.description or f'At most {max_per_draft} "{ch}" per draft; the first is kept.',
                replacement="." if ch in "!?" else "",
            ))
    return hits


def check_length_limit(rule: RuleSpec, text: str, channel: str) -> list[RuleHit]:
    limits = rule.params.get("limits", {}).get(channel)
    if not limits:
        return []
    hits = []
    max_chars = limits.get("max_chars")
    if max_chars and len(text) > max_chars:
        hits.append(RuleHit(
            rule.code, rule.id, rule.severity, max_chars, len(text), text[max_chars:],
            f"{len(text)} characters; {channel} allows {max_chars}",
            rule.description or "The highlighted text is past the channel limit. Shorten the draft.",
        ))
    max_words = limits.get("max_words")
    if max_words:
        words = list(re.finditer(r"\S+", text))
        if len(words) > max_words:
            s = words[max_words].start()
            hits.append(RuleHit(
                rule.code, rule.id, rule.severity, s, len(text), text[s:],
                f"{len(words)} words; {channel} allows {max_words}",
                rule.description or "The highlighted text is past the word limit.",
            ))
    return hits


def check_readability(rule: RuleSpec, text: str, channel: str) -> list[RuleHit]:
    max_words = rule.params.get("max_sentence_words", 30)
    min_flesch = rule.params.get("min_flesch")
    hits = []
    sents = split_sentences(text)
    for s in sents:
        n = len(s.text.split())
        if n > max_words:
            hits.append(RuleHit(
                rule.code, rule.id, rule.severity, s.start, s.end, s.text,
                f"Long sentence ({n} words; limit {max_words})",
                rule.description or "Split this sentence so it is easier to read.", ai_fixable=True,
            ))
    if min_flesch is not None and len(text.split()) >= 30 and sents:
        score = textstat.flesch_reading_ease(text)
        if score < min_flesch:
            longest = max(sents, key=lambda s: len(s.text.split()))
            if not any(h.start == longest.start for h in hits):
                hits.append(RuleHit(
                    rule.code, rule.id, rule.severity, longest.start, longest.end, longest.text,
                    f"Hard to read (Flesch {score:.0f}; target {min_flesch}+)",
                    rule.description or "Use shorter words and sentences. The longest sentence is highlighted.",
                    ai_fixable=True, extra={"flesch": round(score, 1)},
                ))
    return hits


def check_all_caps(rule: RuleSpec, text: str, channel: str) -> list[RuleHit]:
    allow = {a.upper() for a in rule.params.get("allow", [])}
    min_len = rule.params.get("min_length", 4)
    excluded = _excluded_ranges(text)
    hits = []
    for m in re.finditer(r"\b[A-Z][A-Z']+\b", text):
        word = m.group(0)
        if len(word) < min_len or word in allow or _inside(excluded, *m.span()):
            continue
        hits.append(RuleHit(
            rule.code, rule.id, rule.severity, m.start(), m.end(), word,
            f'All caps: "{word}"', rule.description or "Avoid shouting in capitals.",
            replacement=word.capitalize(),
        ))
    return hits


def check_hashtag(rule: RuleSpec, text: str, channel: str) -> list[RuleHit]:
    tags = list(re.finditer(r"(?<!\w)#\w+", text))
    hits = []
    max_count = rule.params.get("max_count")
    if max_count is not None and len(tags) > max_count:
        first, last = tags[max_count], tags[-1]
        hits.append(RuleHit(
            rule.code, rule.id, rule.severity, first.start(), last.end(), text[first.start():last.end()],
            f"{len(tags)} hashtags; limit {max_count}",
            rule.description or f"Use at most {max_count} hashtags. The extra ones are highlighted.",
        ))
    present = {t.group(0).lower() for t in tags}
    missing = [r for r in rule.params.get("required", []) if r.lower() not in present]
    if missing:
        hit = _append_hit(rule, text, " ".join(missing), f"Missing hashtag {', '.join(missing)}",
                          rule.description or "Brand posts carry the brand hashtag.")
        if hit:
            hits.append(hit)
    return hits


def _regex_flags(flags: str) -> int:
    return (re.IGNORECASE if "i" in flags else 0) | (re.MULTILINE if "m" in flags else 0)


def check_regex(rule: RuleSpec, text: str, channel: str) -> list[RuleHit]:
    pat = re.compile(rule.params["pattern"], _regex_flags(rule.params.get("flags", "")))
    template = rule.params.get("replacement")
    hits = []
    for m in pat.finditer(text):
        if m.end() == m.start():
            continue
        hits.append(RuleHit(
            rule.code, rule.id, rule.severity, m.start(), m.end(), m.group(0),
            rule.params.get("message") or rule.title or "Pattern not allowed",
            rule.description, replacement=m.expand(template) if template is not None else None,
        ))
    return hits


CURRENCY_PRESET = re.compile(r"(?<!\w)(?:Rs\.?|INR)\s?(\d[\d,]*(?:\.\d+)?)", re.IGNORECASE)


def check_currency_format(rule: RuleSpec, text: str, channel: str) -> list[RuleHit]:
    symbol = rule.params.get("symbol", "₹")
    return [
        RuleHit(rule.code, rule.id, rule.severity, m.start(), m.end(), m.group(0),
                f'Write prices as "{symbol}{m.group(1)}"', rule.description or "Use the rupee symbol for prices.",
                replacement=f"{symbol}{m.group(1)}")
        for m in CURRENCY_PRESET.finditer(text)
    ]


CHECKS: dict[str, Callable[[RuleSpec, str, str], list[RuleHit]]] = {
    "terminology": check_terminology,
    "banned_phrase": check_banned_phrase,
    "required_phrase": check_required_phrase,
    "punctuation_limit": check_punctuation_limit,
    "length_limit": check_length_limit,
    "readability": check_readability,
    "all_caps": check_all_caps,
    "hashtag": check_hashtag,
    "regex": check_regex,
    "currency_format": check_currency_format,
}


def run_rules(text: str, channel: str, rules: list[RuleSpec]) -> list[RuleHit]:
    hits: list[RuleHit] = []
    for rule in rules:
        if rule.channels and channel not in rule.channels:
            continue
        hits.extend(CHECKS[rule.type](rule, text, channel))
    hits.sort(key=lambda h: (h.start, h.end, h.code))
    return hits


def validate_rule(rule_type: str, params: dict) -> list[str]:
    """Return a list of problems. Regex rules must compile and pass their own test strings."""
    errors: list[str] = []
    if rule_type not in CHECKS:
        return [f"Unknown rule type {rule_type}"]
    required = {
        "terminology": ["preferred"], "banned_phrase": ["phrases"], "required_phrase": ["text"],
        "length_limit": ["limits"], "regex": ["pattern"],
    }.get(rule_type, [])
    errors += [f"Missing parameter: {k}" for k in required if not params.get(k)]
    for key in ("pattern", "trigger"):
        if params.get(key):
            try:
                re.compile(params[key])
            except re.error as e:
                errors.append(f"{key} is not a valid regex: {e}")
    if rule_type == "regex" and not errors:
        pat = re.compile(params["pattern"], _regex_flags(params.get("flags", "")))
        for s in params.get("should_match", []):
            if not pat.search(s):
                errors.append(f'Pattern does not match test string "{s}"')
        for s in params.get("should_not_match", []):
            if pat.search(s):
                errors.append(f'Pattern wrongly matches "{s}"')
    return errors
