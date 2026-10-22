"""Checks every suggested fix must pass before the UI shows it."""
import json
import re

from app.lanes.rules.engine import RuleSpec, run_rules
from app.llm import adapter
from app.llm.prompts import INTENT_SYSTEM, INTENT_VERSION
from app.schemas.llm import IntentOut

NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
MIN_INTENT = 4


def _numbers(s: str) -> set[str]:
    return {n.replace(",", "") for n in NUMBER.findall(s)}


def number_guard(replacement: str, original_span: str, evidence_statements: list[str]) -> bool:
    """Every number in the fix must already be in the original span or in a cited fact."""
    allowed = _numbers(original_span)
    for st in evidence_statements:
        allowed |= _numbers(st)
    return _numbers(replacement) <= allowed


def apply(text: str, start: int, end: int, replacement: str) -> str:
    return text[:start] + replacement + text[end:]


def rules_recheck(text: str, start: int, end: int, replacement: str, channel: str, rules: list[RuleSpec]) -> bool:
    """The fix must not add a rule finding in the region it rewrites (length limits are judged on the whole draft)."""
    scoped = [r for r in rules if r.type != "length_limit"]
    before = {(h.code, h.span_text) for h in run_rules(text, channel, scoped) if h.start < end and start < h.end}
    patched = apply(text, start, end, replacement)
    lo, hi = start, start + max(len(replacement), 1)
    after = {(h.code, h.span_text) for h in run_rules(patched, channel, scoped) if h.start < hi and lo < h.end}
    return not (after - before)


def sentence_window(text: str, start: int, end: int) -> tuple[int, int]:
    """Sentence-ish window around a span: from the previous terminator/newline to the next one."""
    lo = max(text.rfind(c, 0, start) for c in ".!?\n") + 1
    nxt = [i for i in (text.find(c, end) for c in ".!?\n") if i >= 0]
    hi = (min(nxt) + 1) if nxt else len(text)
    return lo, hi


async def intent_scores(purpose: str, pairs: list[tuple[str, str]], cache_extra: str) -> dict[int, int]:
    if not pairs:
        return {}
    payload = [{"fix_index": i, "original": o, "rewritten": r} for i, (o, r) in enumerate(pairs)]
    out, _ = await adapter.generate_json(
        system=INTENT_SYSTEM,
        user=f"Purpose line: {purpose}\n<fixes>\n{json.dumps(payload, ensure_ascii=False, indent=1)}\n</fixes>",
        schema=IntentOut, prompt_version=INTENT_VERSION, cache_extra=cache_extra,
    )
    return {s.fix_index: s.intent_score for s in out.scores}
