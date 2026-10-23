# Deployment: Cloudflare Pages + Render, with PR previews

```
Browser ──► https://<project>.pages.dev                 (Cloudflare Pages)
              ├─ /*      static SPA from frontend/dist
              └─ /api/*  Pages Function frontend/functions/api/[[path]].ts
                           │  same-origin proxy, forwards cookies and client IP
                           ▼
            https://countersign-rpcj.onrender.com       (Render web service: FastAPI + review worker)
                           ▼
            Neon Postgres + pgvector  (main branch for production, a "preview" branch for PRs)
```

The browser only ever talks to the Pages origin. That keeps the [ADR-001](decisions/ADR-001-single-container.md) guarantees
(no CORS, first-party `SameSite=Lax` session cookie) even though the API lives on Render. A direct
cross-origin call from `pages.dev` to `onrender.com` needs `SameSite=None` cookies, which Safari and
Chrome's third-party-cookie blocking drop, so demo sign-in silently fails for some judges.

| Event | Frontend | Backend |
|---|---|---|
| Push to `main` | GitHub Action deploys `https://<project>.pages.dev` | Render auto-deploys the service |
| PR #n opened / updated | GitHub Action deploys `https://pr-n.<project>.pages.dev` and comments the link | Render creates `countersign-rpcj-pr-n.onrender.com` |
| PR closed | Pages deployment stays (harmless) | Render deletes the preview |

---

## 1. Database (Neon)

**Put Neon and Render in the same region.** A review makes many sequential queries; with
Render in Oregon and Neon in Sydney each round trip costs ~0.5 s and a review takes over a minute.
Render Oregon pairs with Neon `aws-us-west-2`; Render Singapore with Neon `aws-ap-southeast-1`.
A Neon project's region cannot be changed: create a new project there and point `DATABASE_URL` at it
(demo sandboxes are rebuilt automatically; rerun `make seed` if you use a persistent workspace).

1. Production: the existing Neon `main` branch. Copy its connection string (pooled is fine).
2. Previews: in Neon, **Branches → Create branch** `preview` from `main`. Copy its connection string.
   All PR previews share this branch. Reset it from `main` whenever a PR's migration leaves it messy.

`alembic upgrade head` runs on every start and creates the `vector` extension itself.

## 2. Backend (Render)

### Service settings (Dashboard → countersign → Settings)

| Setting | Value |
|---|---|
| Runtime | Python 3 (pinned to 3.12 by `backend/.python-version`) |
| Root directory | `backend` |
| Build command | `pip install -r requirements.txt` (add `-r requirements-ml.txt` only on 2 GB+ instances; on the free 512 MB plan fastembed + spaCy can run out of memory, and the app falls back to hashed embeddings and regex PII) |
| Start command | `python -m alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips='*'` |
| Health check path | `/api/health` |
| Auto-deploy | On commit, branch `main` |

Alternative: Docker runtime with `Dockerfile.backend` (includes the ML models, needs more memory).

### Environment variables

| Key | Value |
|---|---|
| `DATABASE_URL` | Neon `main` connection string |
| `PREVIEW_DATABASE_URL` | Neon `preview` connection string |
| `JWT_SECRET` | long random string (`python -c "import secrets; print(secrets.token_urlsafe(48))"`) |
| `COOKIE_SECURE` | `true` |
| `COOKIE_SAMESITE` | `lax` (or leave unset) |
| `CORS_ORIGINS` | leave **unset**: the proxy makes requests same-origin |
| `GEMINI_API_KEY` | key from a billing-enabled project with a spend cap |
| `LLM_PRIMARY_MODEL` / `LLM_FALLBACK_MODEL` | `gemini-3.5-flash` / `gemini-3.5-flash-lite` |
| `EMBEDDINGS` / `PII_ENGINE` | `auto` |
| `SANDBOX_POOL_SIZE` | `2` |

### PR previews

Dashboard → service → **Settings → Pull Request Previews → Automatic**. Render then builds every PR
against the same repo as `<service>-pr-<n>.onrender.com` and posts that URL on the PR; check that
it matches `PREVIEW_API_HOST` below (if your service slug has a random suffix, it is part of the
pattern).

Previews **copy every environment variable** of the base service, including `DATABASE_URL`. Render
also sets `IS_PULL_REQUEST=true` on them, and `app/config.py` then switches to
`PREVIEW_DATABASE_URL`. If that variable is missing, the preview refuses to start rather than run a
PR branch's migrations on production data.

Previews share the Gemini key and its quota. A preview on the free plan sleeps like production;
its first request after idle takes ~1 minute.

## 3. Frontend (Cloudflare Pages)

The project is a **Direct Upload** project deployed by `.github/workflows/pages.yml`, because only
CI knows the PR number that Render uses in preview hostnames. (A Git-connected Pages project names
previews after the branch, so it cannot point a preview at the matching Render PR.)

### One-time setup

1. Create the project (skip if a Direct Upload project already exists):

   ```bash
   npx wrangler@4 pages project create countersign --production-branch main
   ```

   If your current Pages project is Git-connected, create a new Direct Upload one like this, or
   turn off its automatic builds (Settings → Builds → Branch control) so the two do not fight.

2. Pages project → **Settings → Variables and Secrets**, for both *Production* and *Preview*:

   | Name | Value |
   |---|---|
   | `API_ORIGIN` | optional; defaults to `https://countersign-rpcj.onrender.com` (set in the Function) |
   | `PREVIEW_API_HOST` | `countersign-rpcj-pr-{n}.onrender.com` |

   `VITE_API_URL` is ignored: the SPA always calls relative `/api/...` and the Function forwards it.
   Delete it from the Pages settings to avoid confusion.

3. GitHub repo → **Settings → Secrets and variables → Actions**:

   | Kind | Name | Value |
   |---|---|---|
   | Secret | `CLOUDFLARE_API_TOKEN` | API token with **Account → Cloudflare Pages → Edit** |
   | Secret | `CLOUDFLARE_ACCOUNT_ID` | Dashboard → Workers & Pages → right sidebar |
   | Variable | `CF_PAGES_PROJECT` | `countersign` (the project name) |

SPA deep links (`/drafts/123`) work without a `_redirects` file: Pages serves `index.html` for
unknown paths when the build has no `404.html`.

### How a PR preview finds its API

The workflow deploys PR *n* with `--branch pr-n`, which gives the alias `pr-n.<project>.pages.dev`.
The Function reads `pr-n` from the hostname and proxies to `PREVIEW_API_HOST` with `{n}` filled in.
Every other hostname (production, the per-commit `<hash>.<project>.pages.dev` URLs) uses
`API_ORIGIN`. Fork PRs get no secrets and are skipped.

## 4. Verify

Locally, the same proxy runs with `cd frontend && npm run build && npx wrangler@4 pages dev dist --port 8788`
(add `--binding API_ORIGIN=http://localhost:8000` to use a local backend). Open http://localhost:8788.


```bash
curl https://<project>.pages.dev/api/health            # {"ok":true}  (proxied to Render)
curl https://<project>.pages.dev/api/health/deep       # db, pgvector, embeddings, LLM status
make smoke URL=https://<project>.pages.dev             # full judge path through the proxy
```

Then open the site in a private window, click **Try as Creator**, and confirm you stay signed in
after a reload.

## Troubleshooting

| Symptom (Render logs) | Cause | Fix |
|---|---|---|
| `GET //api/me 404`, `POST //api/demo/session 404` | `VITE_API_URL` set with a trailing slash, so the SPA calls Render directly with `//api` | Fixed: the SPA no longer reads `VITE_API_URL`; redeploy Pages |
| `OPTIONS /api/... 400` | Browser preflight from a cross-origin page whose origin is not in `CORS_ORIGINS` | Use the proxy (no preflight at all) |
| `POST /api/demo/session` takes ~90 s | Sandbox pool empty, so a sandbox (with LLM-reviewed sample drafts) is built inside the request | Raise `SANDBOX_POOL_SIZE` before judging |
| Demo sign-in works, next request is 401 | Cross-site cookie blocked | Use the proxy; `COOKIE_SAMESITE=lax` |
| `GET / 404` on the Render URL | Expected: the Python runtime does not build the SPA; Pages serves it | Open the Pages URL instead |
| `fastembed unavailable ... using hashed embeddings` | ML requirements not installed | Fine on the free plan; see build command above |
| Preview crashes with `PR preview without PREVIEW_DATABASE_URL` | Guard in `app/config.py` | Add `PREVIEW_DATABASE_URL` to the base service |
| Reviews take 60 s+, `/api/health/deep` takes ~2 s | Render and Neon in different regions | Move Neon next to Render (section 1) |
| Gemini `429 Too Many Requests` | Primary model quota | The fallback model takes over; raise the quota or lower `LLM_CONCURRENCY` |
