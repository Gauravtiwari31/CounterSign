"""Voice lane: advisory only. Severity is fixed in code; the model has no severity field."""
import json

from app.lanes.text import locate
from app.lanes.types import NewFinding
from app.llm import adapter
from app.llm.prompts import VOICE_SYSTEM, VOICE_VERSION
from app.models import VoiceCriterion
from app.pii import Masker
from app.schemas.llm import VoiceNote, VoiceOut


def build_user_prompt(text: str, criteria: list[VoiceCriterion], masker: Masker) -> str:
    rubric = [
        {"code": c.code, "title": c.title, "description": c.description,
         "good_examples": c.good_examples, "bad_examples": c.bad_examples}
        for c in criteria
    ]
    return ("Brand voice rubric:\n" + json.dumps(rubric, ensure_ascii=False, indent=1)
            + f"\n\n<draft>\n{masker.mask(text)}\n</draft>")


async def run_voice(text: str, criteria: list[VoiceCriterion], masker: Masker, cache_extra: str) -> list[NewFinding]:
    if not criteria or not text.strip():
        return []
    out, meta = await adapter.generate_json(
        system=VOICE_SYSTEM, user=build_user_prompt(text, criteria, masker), schema=VoiceOut,
        prompt_version=VOICE_VERSION, cache_extra=cache_extra,
    )
    return notes_to_findings(out.notes, criteria, text, masker, meta)


def notes_to_findings(notes: list[VoiceNote], criteria: list[VoiceCriterion], text: str, masker: Masker,
                      meta: adapter.CallMeta) -> list[NewFinding]:
    titles = {c.code: c.title for c in criteria}
    findings = []
    for n in notes[:5]:
        if n.criterion_code not in titles:
            continue
        span = locate(masker.unmask(n.quote), text)
        if span is None:
            continue
        replacement = masker.unmask(n.suggestion) if n.suggestion else None
        findings.append(NewFinding(
            lane="voice", severity="advisory", source="ai", start=span[0], end=span[1],
            span_text=text[span[0]:span[1]], criterion_code=n.criterion_code,
            message=f"{n.criterion_code} · {titles[n.criterion_code]}", explanation=n.note,
            suggestion={"replacement": replacement, "kind": "ai", "recheck": None} if replacement else None,
            model=meta.model, prompt_version=meta.prompt_version,
        ))
    return findings
