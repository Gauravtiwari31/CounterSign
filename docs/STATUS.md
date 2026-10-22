# Status: Round 1 plan vs Round 2 build

## What ships

| Round 1 P0 item | Round 2 | Status |
|---|---|---|
| Workspace and roles | Org-scoped data; Admin / Reviewer / Creator; JWT cookie auth; password login for real workspaces; per-visitor demo sandboxes with a role switcher | ✓ |
| Rulebook (versioned) | 10 deterministic rule types; copy-on-write versions; each review stores its rulebook version; "Test this rule" box; regex rules validated against their own test strings on save | ✓ |
| Evidence library | Facts with source, locator, owner, product/channel/region scope, valid_from/valid_to, superseded_by; local embeddings; copy-on-write versions | ✓ |
| Submission | Paste, DOCX, PDF (≤ 5 MB, stored org-scoped in Postgres); channel; purpose line; one-click Round 1 example | ✓ |
| Three-lane review | Rules inline (~6 ms), claims (AI + code verification), voice (advisory, cannot block); inline highlights with text badges | ✓ |
| Intent-preserving fixes | Deterministic rule fixes; batched AI fixes with number guard, rules re-check, claims re-check and intent score ≥ 4 | ✓ |
| Countersign workflow | Accept / dismiss (reason) / override (reason) / reopen; comments; request changes / approve / reject; claims ledger + "reviewed all claims"; version diff; append-only hash-chained audit log | ✓ |
| Privacy and disclosure | PII masked before LLM calls with allow-list; "AI" / "Rule" / "Pattern" label on every finding; Settings lists every external service | ✓ |
| Evaluation harness | 3 fictional brands, 36 labelled drafts (the Round 1 minimum), `make eval` with per-lane P/R, confusion matrix, injection pass rate, latency, LLM usage | ✓ (36 of 60 drafts; labels pending human verification) |
| Export | CSV and printable HTML review record for approved drafts | ✓ |
| Brand palette contrast check | Admin palette editor with a WCAG 2.1 contrast matrix (AA / AA large / AAA written as Pass/Fail) | ✓ |
| Alt-text check | Moved to Round 3 with the visual pack (text drafts have no images) | moved |

## What does not work yet

- **LLM keys are not set in this repository.** Without `GEMINI_API_KEY` (or `GROQ_API_KEY`) the claims lane runs the deterministic pattern fallback: every claim is flagged UNSUPPORTED "needs human review", voice notes are unavailable and AI fixes are not offered. The banner says so. The published eval numbers were produced in this mode; the AI-mode numbers must be re-run with a key before they are quoted anywhere.
- **The Round 1 caption is a reconstruction.** `backend/app/seed/brands/verdant_skin.yaml` → `sample` was rebuilt from the facts named in the plan (AloeCalm, F-12, F-19, F-23, R03, R07). Replace it with the exact text from the Round 1 PDF §4.1.
- **Eval labels were proposed by an AI assistant**, not written independently by two humans as planned. They must be reviewed by two team members and the agreement % recorded (see `eval/README.md`).
- **Eval set is 36 drafts**, the Round 1 minimum, not the 60 targeted.
- **User tests and field validation have not been run.** `docs/USER_TESTING.md` and `docs/FIELD_VALIDATION.md` are templates.
- Images inside DOCX/PDF are ignored; scanned PDFs (no text layer) are rejected with a message.
- Voice notes can vary between runs (temperature 0, but provider-side changes are possible).
- Rule parameters are edited as JSON with a per-type template rather than fully type-specific forms.
- No deployment yet: hosting (AWS vs Hugging Face Spaces), Neon database and keep-warm pinger still need to be set up.

## Changes from Round 1 (change log)

| Round 1 plan | Round 2 reality | Why |
|---|---|---|
| Separate worker process + job queue | Worker runs as an async task in the API process, still on a Postgres queue | One container for reliable hosting; splitting it out needs no code change |
| MinIO/S3 private storage | Uploads stored in Postgres (bytea, ≤ 5 MB, org-scoped) | Private by construction, one fewer service |
| Retrieval filtered by validity date | Retrieval includes expired facts; expiry decided in code | Outdated claims show as EXPIRED instead of UNSUPPORTED (ADR-003) |
| Top 5 facts per claim | Top 8 after RRF and scope filtering | Better recall on products with many facts; the judge prompt stays small |
| Alt-text check in the rules lane | Moved to the Round 3 visual pack | Text-only drafts have no images |
| Sentence-level fallback | Clause-level pattern fallback | Reviewers see the exact words that need evidence |
| (new) | Per-visitor demo sandboxes + role switcher, pre-built pool | Judges need no accounts and cannot collide (ADR-004) |
| (new) | Hash-chained audit log, DB-enforced append-only | Tamper-evident history at almost no cost |
| (new) | Number guard on AI fixes | Stops fixes from inventing statistics |
| (new) | Decisions carry over to the same finding on the next version | Creators don't re-dismiss the same item after every edit |
| Single POST for paste and upload | `POST /api/drafts` (JSON) and `POST /api/drafts/upload` (multipart) | Simpler validation for each |
| TypeScript types generated from OpenAPI | Hand-written types mirroring the Pydantic schemas | Faster to iterate; generation can be added with `openapi-typescript` |

## Round 3 commitments

1. **Visual check pack:** OCR on creatives, the same three lanes on image text with box highlights, palette ΔE and text-contrast checks, alt-text checks. *Done when* an image claim gets the same label as the same text claim on ≥ 90% of a 20-image set.
2. **Brand-book import assistant:** PDF guidelines → proposed rules and facts, each with a verified page + quote; admin approves every proposal. *Done when* ≥ 80% of hand-listed rules are proposed on 3 brand books.
3. **Governance insights:** rules to clarify (dismissal/override rates, disagreement) and fact-change impact (re-open every approved draft that relied on a changed or expired fact). *Done when* editing F-23 flags every approved draft that cited it.
