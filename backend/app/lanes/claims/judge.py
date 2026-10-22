"""Step 3 - Judge (AI), one batched call per draft."""
import json

from app.lanes.types import Claim
from app.llm import adapter
from app.llm.prompts import CLAIMS_JUDGE_SYSTEM, CLAIMS_JUDGE_VERSION
from app.schemas.llm import JudgeOut, Verdict


def build_user_prompt(claims: list[Claim]) -> str:
    payload = [
        {
            "claim_index": i, "claim": c.atomic, "claim_type": c.claim_type,
            "candidates": [{"fact_code": f.code, "statement": f.statement} for f in c.candidates],
        }
        for i, c in enumerate(claims)
    ]
    return "Judge each claim against its candidate facts.\n<claims>\n" + json.dumps(payload, ensure_ascii=False, indent=1) + "\n</claims>"


async def judge_claims(claims: list[Claim], cache_extra: str) -> tuple[dict[int, Verdict], adapter.CallMeta | None]:
    if not claims:
        return {}, None
    out, meta = await adapter.generate_json(
        system=CLAIMS_JUDGE_SYSTEM, user=build_user_prompt(claims), schema=JudgeOut,
        prompt_version=CLAIMS_JUDGE_VERSION, cache_extra=cache_extra,
    )
    return {v.claim_index: v for v in out.verdicts if 0 <= v.claim_index < len(claims)}, meta
