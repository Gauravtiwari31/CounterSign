# ADR-005: Compact mode, one LLM call per review

**Status:** accepted (changes the Round 1 plan, which used separate extract, judge, voice and fix calls)

**Context.** The demo runs on the free Gemini tier, which limits requests per model per day (20 for gemini-3.5-flash). The original pipeline made about 7 calls per review (extract, judge, voice, fix, re-check extract, re-check judge, intent), so the live site fell back to the pattern detector after about 3 reviews a day. That fallback labels every claim UNSUPPORTED, which also dragged the October 22 eval down to claims recall 0.66.

**Decision.** `LLM_MODE=compact` (the default) does the AI work in one call: the model extracts claims, judges them against candidate facts that code chose for each sentence, writes voice notes and proposes fixes. A second call runs only when a proposed fix has passed the number guard and the rules re-check; it checks claims in the rewritten sentences and scores intent together. The facts sent to the model carry no validity dates: shown an expired fact, the model labelled matching claims CONTRADICTED instead of letting code label them EXPIRED (7 of 9 expired claims in the first compact run). `LLM_MODE=full` keeps the original pipeline.

**What did not change.** Every code check still applies: quotes must be found in the draft, evidence quotes must appear word for word in a fact retrieved for that sentence and in the claim's product scope, expiry and severity are decided in code, voice notes are always advisory, and fixes pass the number guard, the rules re-check, a claims re-check and intent ≥ 4.

**Consequences.** On the 36-draft eval (2026-10-24, flash-lite) compact mode used 43 calls instead of 143, had no fallback drafts instead of 9, and scored claims recall 0.915 and precision 0.956 (full mode the same day: 0.787 / 0.755), with full-review p95 down from 22.4 s to 10.2 s. The cost is less independence: the model that proposes a fix no longer also writes a separate judgement, so the second call and the code checks carry the verification. Libraries over 30 facts fall back to retrieval per sentence, which can miss a fact that a claim paraphrases.
