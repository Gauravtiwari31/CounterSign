# Architecture as built

## Runtime

One container serves the API and the built React SPA from the same origin, so there is no CORS and the judge's link and the API share cookies. The review worker is an asyncio task inside the API process; it polls a Postgres queue with `SELECT … FOR UPDATE SKIP LOCKED`. Running it as its own process is `python -m app.worker`.

```
backend/app
├─ main.py            FastAPI app, SPA mount, starts the worker
├─ api/               routes_{auth,demo,drafts,review,workflow,admin,export,health}
├─ deps.py            current principal (JWT cookie) · require_role · in-process rate limiter
├─ review.py          create_version (rules inline) · run_ai_lanes (worker) · decision carry-over
├─ worker.py          queue loop, retries, stale-lock recovery, sandbox housekeeping
├─ workflow/state.py  pure state machine + guards (unit-tested per transition x role)
├─ audit.py           append_event with per-org hash chain · verify_chain
├─ lanes/
│  ├─ text.py         canonical text, spaCy sentencizer with offsets, locate() quote -> span
│  ├─ rules/engine.py 10 deterministic rule types, validate_rule
│  ├─ claims/         extract · retrieve · judge · verify · label · heuristics · pipeline
│  ├─ voice/review.py advisory notes
│  └─ fixes/          deterministic + AI fixes, number guard, re-checks, intent score
├─ llm/               provider adapter (cache -> primary -> fallback), versioned prompts
├─ pii.py             Presidio + regex masking with allow-list, reversible per job
├─ embeddings.py      fastembed bge-small-en-v1.5 (384-d), hashed fallback
└─ seed/              brand YAML, loader, sandbox pool, CLI for persistent workspaces
```

## Data

PostgreSQL 16 with pgvector. Every organisation-owned row carries `org_id`; every route resolves resources through the caller's organisation, and a test walks the route table to prove another organisation gets 404.

- **Copy-on-write versioning.** Editing a rule, fact or voice criterion retires the old row (`retired_in = new version`) and inserts a new one. A row is active at version *v* when `introduced_in <= v < retired_in`. Every draft version stores the rulebook and facts versions it was checked against.
- **Facts** keep `valid_from`, `valid_to` and `superseded_by`. Retrieval deliberately includes expired and superseded facts; the label step decides expiry in code, which is how an outdated claim shows up as EXPIRED instead of UNSUPPORTED.
- **Audit log** is append-only: a trigger raises on `UPDATE`/`DELETE`/`TRUNCATE` (the one exception is the retention purge of an expired demo sandbox). Each event stores `hash = sha256(prev_hash || canonical_json(event))`; History shows the chain verification result.

## The claims pipeline

1. **Extract (AI).** Numbered, PII-masked sentences inside `<draft>` delimiters. The model returns quotes, never offsets. Code unmasks each quote and locates it inside its sentence (exact → normalised quotes/dashes/whitespace → fuzzy ≥ 95 with matching numbers); unlocatable claims are dropped.
2. **Retrieve (code).** Per claim: full-text (`ts_rank` over an OR-query) and vector (`<=>` cosine) top 10, fused with Reciprocal Rank Fusion (k = 60), scope-filtered by product/channel/region, top 8 kept.
3. **Judge (AI).** One batched call: supports / contradicts / insufficient, a fact code and an evidence quote.
4. **Verify (code).** The fact code must be one of that claim's candidates and the normalised quote must be a substring of the normalised fact statement (min 6 characters). Otherwise the verdict is downgraded to UNSUPPORTED with "Model cited evidence that could not be verified". Citation validity is 100% by construction.
5. **Label (code).** supports + valid → SUPPORTED (info) · supports + expired/superseded → EXPIRED · contradicts → CONTRADICTED · anything else → UNSUPPORTED. A regulatory review prompt is attached by claim type (CCPA greenwashing guidelines, ASCI substantiation, free-offer conditions), always marked "not legal advice".

If both providers fail, a clause-level pattern detector flags claims as UNSUPPORTED "needs human review" and the UI shows a banner with **Retry AI checks**.

## LLM calls per review

extract · judge · voice (parallel with claims) · fix generation · re-check extract · re-check judge · intent score. All are cached by `sha256(prompt_version | model | masked input | rulebook version | facts version)`, so unchanged sentences and the seeded sandbox drafts cost nothing after the first run.

## Demo sandboxes

`POST /api/demo/session` claims a pre-built sandbox from a small pool (the worker keeps `SANDBOX_POOL_SIZE` ready) and sets a cookie for the chosen role. Each sandbox is a full copy of Verdant Skin with drafts in every state. Sandboxes expire after 48 hours and are purged by the worker.
