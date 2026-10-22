# ADR-001: One container for API, SPA and review worker

**Status:** accepted

**Context.** Judges open one link and must finish the journey without help. Separate frontend and API hosts add CORS, cookie and cold-start failure modes; a separate worker process doubles the deploy surface on free hosts.

**Decision.** FastAPI serves `/api/*` and the built SPA from one container. The review worker is an asyncio task in the same process, consuming a Postgres queue with `SKIP LOCKED`.

**Consequences.** One URL, one deploy, no CORS. Throughput is bounded by one process, which is ample for the demo. The worker is its own module (`python -m app.worker`), so splitting it out later is a Dockerfile change, not a code change.
