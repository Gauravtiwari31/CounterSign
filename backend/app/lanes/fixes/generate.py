"""Intent-preserving fixes.

1. Deterministic first (rules with a replacement).
2. One batched AI call for the remaining blocking/warning findings, given only verified evidence.
3. Number guard, rules re-check, claims re-check on the changed sentence, intent score >= 4.
4. Anything that fails shows "No safe automatic fix" with an approach - never a broken fix.
"""
import asyncio
import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.lanes.claims.extract import extract_claims
from app.lanes.claims.pipeline import judge_and_label
from app.lanes.context import ReviewContext
from app.lanes.fixes.recheck import MIN_INTENT, apply, intent_scores, number_guard, rules_recheck, sentence_window
from app.lanes.text import Sentence
from app.lanes.types import NewFinding
from app.llm import adapter
from app.llm.adapter import LLMUnavailable
from app.llm.prompts import FIX_SYSTEM, FIX_VERSION
from app.pii import Masker
from app.schemas.llm import FixOut

log = logging.getLogger("countersign.fixes")
FIXABLE_LABELS = {"UNSUPPORTED", "CONTRADICTED", "EXPIRED"}


def deterministic_suggestion(f: NewFinding, replacement: str, text: str, ctx: ReviewContext) -> dict:
    ok = rules_recheck(text, f.start, f.end, replacement, ctx.channel, ctx.rules)
    return {"replacement": replacement, "kind": "deterministic",
            "recheck": {"rules_ok": ok, "claims_ok": None, "intent_score": None}} if ok else no_fix(
        "The automatic replacement would trigger another rule. Edit this text by hand.")


def no_fix(approach: str | None) -> dict:
    return {"replacement": None, "kind": "ai",
            "approach": "No safe automatic fix. Suggested approach: " + (approach or "rewrite or remove this text, "
                        "keeping only what the approved evidence states."), "recheck": None}


def needs_ai_fix(f: NewFinding) -> bool:
    if f.suggestion is not None:
        return False
    if f.lane == "rules":
        return f.ai_fixable and f.severity in ("blocking", "warning")
    return f.lane == "claims" and f.claim_label in FIXABLE_LABELS


def _evidence_statements(f: NewFinding) -> list[str]:
    return [e["statement"] for e in f.evidence if e.get("verified") and e.get("status") == "valid"]


def build_user_prompt(text: str, purpose: str, targets: list[NewFinding], masker: Masker) -> str:
    items = [
        {"finding_index": i, "flagged_span": masker.mask(f.span_text), "problem": f.message,
         "details": f.explanation, "evidence_you_may_use": _evidence_statements(f)}
        for i, f in enumerate(targets)
    ]
    return (f"Purpose line: {purpose}\n<draft>\n{masker.mask(text)}\n</draft>\nFindings to fix:\n"
            + json.dumps(items, ensure_ascii=False, indent=1))


async def _claims_ok(session: AsyncSession, ctx: ReviewContext, patched_windows: list[tuple[str, int, int]],
                     masker: Masker) -> dict[int, bool]:
    """Extract + judge the rewritten sentences only; a fix fails if its new words carry a non-SUPPORTED claim."""
    sentences = []
    offset = 0
    joined_parts = []
    for i, (window, _, _) in enumerate(patched_windows):
        sentences.append(Sentence(i, offset, offset + len(window), window))
        joined_parts.append(window)
        offset += len(window) + 1
    joined = "\n".join(joined_parts)
    claims, _, _ = await extract_claims(joined, sentences, masker, ctx.cache_extra)
    findings, _ = await judge_and_label(session, ctx, claims, sentences) if claims else ([], {})
    result = {i: True for i in range(len(patched_windows))}
    for f in findings:
        if f.claim_label == "SUPPORTED":
            continue
        idx = next(s.id for s in sentences if s.start <= f.start < s.end + 1)
        _, lo, hi = patched_windows[idx]
        local = f.start - sentences[idx].start, f.end - sentences[idx].start
        if local[0] < hi and lo < local[1]:
            result[idx] = False
    return result


async def ai_fixes(session: AsyncSession, ctx: ReviewContext, text: str, findings: list[NewFinding],
                   masker: Masker) -> dict:
    targets = [f for f in findings if needs_ai_fix(f)]
    stats = {"ai_fix_requested": len(targets), "ai_fix_shown": 0, "number_guard_rejects": 0,
             "rules_recheck_rejects": 0, "claims_recheck_rejects": 0, "intent_rejects": 0}
    if not targets:
        return stats
    try:
        out, meta = await adapter.generate_json(
            system=FIX_SYSTEM, user=build_user_prompt(text, ctx.purpose, targets, masker), schema=FixOut,
            prompt_version=FIX_VERSION, cache_extra=ctx.cache_extra,
        )
    except LLMUnavailable:
        for f in targets:
            f.suggestion = no_fix("AI fixes are unavailable right now. Use the explanation and evidence to rewrite.")
        return stats

    by_index = {fx.finding_index: fx for fx in out.fixes}
    candidates: list[tuple[NewFinding, str]] = []
    for i, f in enumerate(targets):
        fx = by_index.get(i)
        rep = masker.unmask(fx.replacement) if fx and fx.replacement else None
        if rep is None:
            f.suggestion = no_fix(fx.approach if fx else None)
        elif not number_guard(rep, f.span_text, _evidence_statements(f)):
            stats["number_guard_rejects"] += 1
            f.suggestion = no_fix("the rewrite introduced a number that is not in the draft or the evidence. "
                                  + (fx.approach or "Rephrase using only the approved figures."))
        elif not rules_recheck(text, f.start, f.end, rep, ctx.channel, ctx.rules):
            stats["rules_recheck_rejects"] += 1
            f.suggestion = no_fix(fx.approach)
        else:
            candidates.append((f, rep))
    if not candidates:
        return stats

    windows, pairs = [], []
    for f, rep in candidates:
        lo, hi = sentence_window(text, f.start, f.end)
        patched = apply(text, f.start, f.end, rep)
        new_hi = hi + len(rep) - (f.end - f.start)
        windows.append((patched[lo:new_hi].strip("\n"), f.start - lo, f.start - lo + len(rep)))
        pairs.append((text[lo:hi].strip("\n"), patched[lo:new_hi].strip("\n")))
    try:
        # the claims re-check and the intent score are independent: run them side by side
        claims_ok, scores = await asyncio.gather(
            _claims_ok(session, ctx, windows, masker),
            intent_scores(ctx.purpose, [(masker.mask(a), masker.mask(b)) for a, b in pairs], ctx.cache_extra),
        )
    except LLMUnavailable:
        for f, _ in candidates:
            f.suggestion = no_fix("the AI re-check is unavailable, so the rewrite could not be verified.")
        return stats

    for i, (f, rep) in enumerate(candidates):
        score = scores.get(i)
        if not claims_ok.get(i, False):
            stats["claims_recheck_rejects"] += 1
            f.suggestion = no_fix("the rewrite still makes a claim the evidence does not support.")
        elif score is None or score < MIN_INTENT:
            stats["intent_rejects"] += 1
            f.suggestion = no_fix("the safe rewrites found changed the message too much. Keep the purpose and "
                                  "remove only the unsupported part.")
        else:
            stats["ai_fix_shown"] += 1
            f.suggestion = {"replacement": rep, "kind": "ai", "model": meta.model,
                            "recheck": {"rules_ok": True, "claims_ok": True, "intent_score": score}}
    return stats


def guard_voice_suggestions(findings: list[NewFinding], text: str, ctx: ReviewContext) -> None:
    """Voice rewrites are advisory, but still may not add numbers or break rules."""
    for f in findings:
        if f.lane != "voice" or not f.suggestion or not f.suggestion.get("replacement"):
            continue
        rep = f.suggestion["replacement"]
        if not number_guard(rep, f.span_text, []) or not rules_recheck(text, f.start, f.end, rep, ctx.channel, ctx.rules):
            f.suggestion = None
        else:
            f.suggestion["recheck"] = {"rules_ok": True, "claims_ok": None, "intent_score": None}
