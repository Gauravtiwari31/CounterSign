# Status: Round 1 plan vs Round 2 build

## What ships

| Round 1 P0 item | Round 2 | Status |
|---|---|---|
| Workspace and roles | Org-scoped data; Admin / Reviewer / Creator; JWT cookie auth; sign-up creates a workspace and its admin; email + password login; Team page with one-time invite links, role changes, removal and password links; authors cannot approve their own drafts; a persistent demo company for judges | ✓ |
| Rulebook (versioned) | 10 deterministic rule types; copy-on-write versions; each review stores its rulebook version; "Test this rule" box; regex rules validated against their own test strings on save | ✓ |
| Evidence library | Facts with source, locator, owner, product/channel/region scope, valid_from/valid_to, superseded_by; local embeddings; copy-on-write versions | ✓ |
| Submission | Paste, DOCX, PDF (≤ 5 MB, stored org-scoped in Postgres); channel; purpose line; one-click Round 1 example | ✓ |
| Three-lane review | Rules inline (~6 ms), claims (AI + code verification), voice (advisory, cannot block); inline highlights with text badges | ✓ |
| Intent-preserving fixes | Deterministic rule fixes; batched AI fixes with number guard, rules re-check, claims re-check and intent score ≥ 4 | ✓ |
| Countersign workflow | Accept / dismiss (reason) / override (reason) / reopen; comments; request changes / approve / reject; claims ledger + "reviewed all claims"; version diff; append-only hash-chained audit log | ✓ |
| Privacy and disclosure | PII masked before LLM calls with allow-list; "AI" / "Rule" / "Pattern" label on every finding; Settings lists every external service | ✓ |
| Evaluation harness | 3 fictional brands, 60 labelled drafts (the Round 1 target), `make eval` with per-lane P/R, confusion matrix, injection pass rate, latency, LLM usage | ✓ (36 of 60 drafts; labels pending human verification) |
| Export | CSV and printable HTML review record for approved drafts | ✓ |
| Brand palette contrast check | Admin palette editor with a WCAG 2.1 contrast matrix (AA / AA large / AAA written as Pass/Fail) | ✓ |
| Alt-text check | Moved to Round 3 with the visual pack (text drafts have no images) | moved |

## What does not work yet

- **Gemini is on the free tier (20 requests per day for gemini-3.5-flash, more for flash-lite).** Compact mode (the default) spends 1 call per review, or 2 when fixes need verifying, against about 7 before, and skips a model once its daily quota is gone. Heavy testing can still use up both models' quotas for the day, and the claims lane then falls back to the pattern detector until the reset. Billing (with a spend cap) or a Groq fallback key removes the limit. The free tier also lets Google use prompts to improve its products, which must be disclosed while it is in use. Without any working key the claims lane runs the pattern fallback and the UI says so.
- **Latest complete eval (`eval/results/latest.md`, 2026-10-24, compact mode, 36 drafts, 0 fallbacks):** claims recall 0.915 and precision 0.956 (targets 0.80 / 0.75), rules precision 1.0, injection 4/4, full-review p95 10.2 s (target 20 s), 43 LLM calls for 36 drafts. It ran on `gemini-3.5-flash-lite` because flash's daily quota was used up. The full-mode run the same day (`20261024-112207.md`, 143 calls) lost 9 drafts to rate limits; the October 22 figures (recall 0.66) mostly measured fallback drafts.
- **Eval labels were proposed by an AI assistant**, not written independently by two humans as planned. They must be reviewed by two team members and the agreement % recorded (see `eval/README.md`).
- **The 24 drafts added on 2026-10-24 have not had a complete AI run yet.** Both Gemini models hit their daily free quota during that day's testing, so run `make eval` again after the reset to report all 60.
- **User tests and field validation have not been run.** `docs/USER_TESTING.md` and `docs/FIELD_VALIDATION.md` are templates.
- Images inside DOCX/PDF are ignored; scanned PDFs (no text layer) are rejected with a message.
- Voice notes can vary between runs (temperature 0, but provider-side changes are possible).
- Rule parameters are edited as JSON with a per-type template rather than fully type-specific forms.
- **Production runs without the ML extras.** The live site (https://countersign.notwork.world, Render free plan, 512 MB) uses hashed embeddings and regex PII masking, because fastembed and Presidio do not fit in memory. On the eval brands (about 20 facts each) this costs nothing: the gold fact is in the top 8 candidates for 35 of 35 claims with either embedding engine. Larger evidence libraries will need the real model; a 2 GB instance with `requirements-ml.txt` restores it.

## Changes from Round 1 (change log)

| Round 1 plan | Round 2 reality | Why |
|---|---|---|
| Separate worker process + job queue | Worker runs as an async task in the API process, still on a Postgres queue | One container for reliable hosting; splitting it out needs no code change |
| MinIO/S3 private storage | Uploads stored in Postgres (bytea, ≤ 5 MB, org-scoped) | Private by construction, one fewer service |
| Retrieval filtered by validity date | Retrieval includes expired facts; expiry decided in code | Outdated claims show as EXPIRED instead of UNSUPPORTED (ADR-003) |
| Top 5 facts per claim | Top 8 after RRF and scope filtering | Better recall on products with many facts; the judge prompt stays small |
| Alt-text check in the rules lane | Moved to the Round 3 visual pack | Text-only drafts have no images |
| Sentence-level fallback | Clause-level pattern fallback | Reviewers see the exact words that need evidence |
| (new) | Real accounts: sign-up, invite links, Team page; one demo company with three logins | Replaces the per-visitor sandboxes and role switcher of ADR-004 (still in the code behind `DEMO_SANDBOXES`, used by tests) |
| (new) | Hash-chained audit log, DB-enforced append-only | Tamper-evident history at almost no cost |
| (new) | Number guard on AI fixes | Stops fixes from inventing statistics |
| F-23 valid to 31 Oct 2026 (§4.1) | F-23 (free delivery above ₹499) has no end date; the expiring launch offer is F-25 | The demo's fixed caption must stay SUPPORTED after 31 October; EXPIRED is still shown by F-25, F-41 and F-42 |
| (new) | Decisions carry over to the same finding on the next version | Creators don't re-dismiss the same item after every edit |
| Single POST for paste and upload | `POST /api/drafts` (JSON) and `POST /api/drafts/upload` (multipart) | Simpler validation for each |
| TypeScript types generated from OpenAPI | Hand-written types mirroring the Pydantic schemas | Faster to iterate; generation can be added with `openapi-typescript` |

## Round 3 commitments

1. **Visual check pack:** OCR on creatives, the same three lanes on image text with box highlights, palette ΔE and text-contrast checks, alt-text checks. *Done when* an image claim gets the same label as the same text claim on ≥ 90% of a 20-image set.
2. **Brand-book import assistant:** PDF guidelines → proposed rules and facts, each with a verified page + quote; admin approves every proposal. *Done when* ≥ 80% of hand-listed rules are proposed on 3 brand books.
3. **Governance insights:** rules to clarify (dismissal/override rates, disagreement) and fact-change impact (re-open every approved draft that relied on a changed or expired fact). *Done when* editing F-23 flags every approved draft that cited it.
