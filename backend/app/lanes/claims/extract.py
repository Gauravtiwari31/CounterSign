"""Step 1 - Extract (AI). The model quotes; code locates the quote inside its sentence or drops it."""
from app.lanes.text import Sentence, locate
from app.lanes.types import Claim
from app.llm import adapter
from app.llm.prompts import CLAIMS_EXTRACT_SYSTEM, CLAIMS_EXTRACT_VERSION
from app.pii import Masker
from app.schemas.llm import ExtractOut


def build_user_prompt(sentences: list[Sentence], masker: Masker) -> str:
    numbered = "\n".join(f"[{s.id}] {masker.mask(s.text)}" for s in sentences)
    return f"Numbered sentences of the draft:\n<draft>\n{numbered}\n</draft>\nExtract every claim."


async def extract_claims(text: str, sentences: list[Sentence], masker: Masker, cache_extra: str) -> tuple[list[Claim], adapter.CallMeta | None, int]:
    if not sentences:
        return [], None, 0
    out, meta = await adapter.generate_json(
        system=CLAIMS_EXTRACT_SYSTEM, user=build_user_prompt(sentences, masker), schema=ExtractOut,
        prompt_version=CLAIMS_EXTRACT_VERSION, cache_extra=cache_extra,
    )
    by_id = {s.id: s for s in sentences}
    claims: list[Claim] = []
    dropped = 0
    seen: set[tuple[int, int]] = set()
    for c in out.claims:
        sent = by_id.get(c.sentence_id)
        quote = masker.unmask(c.quote)
        span = locate(quote, text, (sent.start, sent.end)) if sent else None
        if span is None:
            dropped += 1
            continue
        if span in seen:
            continue
        seen.add(span)
        claims.append(Claim(
            sentence_id=c.sentence_id, start=span[0], end=span[1], quote=text[span[0]:span[1]],
            claim_type=c.claim_type, atomic=c.atomic_claim, product=masker.unmask(c.product),
        ))
    return claims, meta, dropped

