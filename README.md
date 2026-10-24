# Countersign

**Catch off-brand words and unproven claims before they ship, then get a human countersign.**

Countersign checks marketing copy against a brand's rulebook and its library of approved evidence, suggests fixes that keep the writer's intent, and routes the draft to a reviewer with a tamper-evident audit trail.

- **Live demo:** https://countersign.notwork.world (no sign-up: pick Creator, Reviewer or Admin)
- **Team:** SHIP IT FRIDAY · Inkloom AI brand-governance problem statement, Round 2

```bash
docker compose up --build        # app on http://localhost:8000, Postgres + pgvector included
```

---

## Try it in 3 minutes

1. Open the app and click **Try as Creator**. You get a private sandbox with the fictional brand *Verdant Skin*.
2. The Round 1 worked example (Riya's AloeCalm caption) is pre-loaded. Click **Check this draft**.
3. Rules findings appear instantly; claims and voice findings follow. Each finding carries a text badge (`RULES · R03`, `CLAIM · CONTRADICTED`, `VOICE · V1`), its evidence and, where safe, a fix.
4. Accept fixes (or edit the text), click **Re-check**, then **Send for countersign**.
5. Switch to **Reviewer** in the header. Open the draft from the queue, check the claims ledger, tick *I have reviewed all claims* and **Approve**.
6. Open **History**: version diff, every decision with its reason, and the audit log with its hash chain verified. Approved drafts export as CSV or a printable review record.

A step bar under the header ticks these steps off as you go.

## What it does

| Lane | How | Can block? |
|---|---|---|
| **Rules** | 10 deterministic rule types (terminology, banned and required phrases, punctuation, length, readability, all-caps, hashtags, regex, currency). Runs inline on submit in ~6 ms. | Yes (per rule severity) |
| **Claims** | Code picks candidate facts (Postgres full-text + pgvector, fused with RRF) → AI extracts and judges claims → **code verifies the cited quote word for word** → code labels it SUPPORTED / UNSUPPORTED / CONTRADICTED / EXPIRED and attaches a regulatory review prompt. | Yes |
| **Voice** | AI notes against the brand voice rubric. Severity is fixed to *advisory* in code. | Never |

**Fixes** are deterministic where possible. AI fixes are batched, given only verified evidence, and must pass a number guard (no new numbers), a rules re-check, a claims re-check on the changed sentence and an intent score of at least 4/5. Otherwise the card says "No safe automatic fix" with an approach.

**Workflow:** Draft → Checking → Checked → In review → Approved / Rejected / Changes requested. Blocking findings must be fixed or dismissed with a reason; a reviewer must override each creator dismissal before approving, and must confirm they reviewed every claim. Every transition and decision is written to an append-only, hash-chained audit log (a database trigger blocks `UPDATE`/`DELETE`).

**Privacy:** personal data (names, phones, emails, Aadhaar/PAN-like IDs) is masked before any LLM call and unmasked locally; brand and product names are on an allow-list. Embeddings run locally. Settings → *External services* lists everything that touches content.

**Built for a free API tier:** by default one LLM call reviews a draft (claims, voice and fix proposals together) and a second runs only to verify fixes, so a review costs 1–2 requests instead of about 7. A model whose daily quota is used up is skipped until it resets, short rate limits are waited out, and responses are cached by content hash. `LLM_MODE=full` restores separate extract / judge / voice / fix / re-check calls.

**Reliability:** LLM responses are schema-validated with one repair retry, then the fallback provider, then a deterministic pattern detector that flags claims for human review (the claims lane never silently passes).

## Architecture

```
Browser (React + TypeScript + TipTap)
   │  same origin, httpOnly JWT cookie
   ▼
One container: FastAPI ── /api/* REST, / serves the built SPA
   │  rules lane inline on submit
   │  review worker (asyncio task) ── Postgres queue, SELECT … FOR UPDATE SKIP LOCKED
   │  fastembed bge-small-en-v1.5 (local) · Presidio + Indian regex recognisers
   ▼
Postgres 16 + pgvector (Neon in production)      LLM adapter: Gemini → Groq → pattern fallback
```

Details: [docs/architecture.md](docs/architecture.md) · decisions: [docs/decisions/](docs/decisions/) · hosting (Cloudflare Pages + Render, PR previews): [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)

## Run locally

**Docker (recommended):** `docker compose up --build` then open http://localhost:8000.

**Without Docker:**

```bash
cd backend
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt -r requirements-ml.txt
cp ../.env.example ../.env          # set DATABASE_URL to a Postgres 16 with pgvector
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m uvicorn app.main:app --reload --port 8000
cd ../frontend && npm ci && npm run dev    # http://localhost:5173 (proxies /api)
```

### Environment

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | local compose DB | Plain `postgres://` / Neon URLs are accepted |
| `JWT_SECRET` | dev value | **Set in production** |
| `COOKIE_SECURE` | `false` | `true` behind HTTPS |
| `GEMINI_API_KEY`, `LLM_PRIMARY_MODEL` | `gemini-3.5-flash` | Use a billing-enabled project with a spend cap |
| `LLM_MODE` | `compact` | `compact` (1–2 calls per review) or `full` (~7) |
| `LLM_THINKING_LEVEL` | _(model default)_ | Gemini 3 thinking level (`minimal`, `low`, …); lower is faster |
| `GROQ_API_KEY`, `LLM_FALLBACK_MODEL` | `llama-3.3-70b-versatile` | Optional fallback |
| `EMBEDDINGS` | `auto` | `fastembed` or `hash` (lean fallback) |
| `PII_ENGINE` | `auto` | `presidio` or `regex` |
| `SANDBOX_POOL_SIZE` | `2` | Pre-built demo sandboxes, so the first click is instant |

Without any LLM key the app still runs end to end: the claims lane flags claims by pattern and shows an "AI checks unavailable" banner.

## Tests and evaluation

```bash
make test     # 203 tests: rules table tests, locate/verify, state machine, PII, audit chain,
              # route-table access control, and the full judge path end to end (needs Postgres)
make eval     # per-lane precision/recall, claim-label confusion matrix, injection pass rate, latency
make smoke URL=https://your-deployment   # judge path against a live deployment
```

Latest numbers: [eval/results/latest.md](eval/results/latest.md). The labelling guide and the status of human label verification are in [eval/README.md](eval/README.md).

## Honest status

See [docs/STATUS.md](docs/STATUS.md) for what ships, what does not work yet, and the changes from the Round 1 plan.

## Licence

MIT. All brands, products, facts and people in the demo and evaluation data are fictional.
