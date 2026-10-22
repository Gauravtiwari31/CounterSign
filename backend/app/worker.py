"""Review worker: an asyncio task in the API process, polling a Postgres queue with SKIP LOCKED.

Splitting it into its own process later means running `python -m app.worker` instead.
"""
import asyncio
import logging
from datetime import timedelta

from sqlalchemy import or_, select

from app.config import get_settings
from app.db import SessionLocal
from app.models import ReviewJob, utcnow
from app.review import run_ai_lanes

log = logging.getLogger("countersign.worker")
MAX_ATTEMPTS = 3
STALE_AFTER = timedelta(minutes=2)
_wake = asyncio.Event()


def wake() -> None:
    """Called after a submit so the job starts without waiting for the next poll."""
    _wake.set()


async def claim_job() -> int | None:
    async with SessionLocal() as session:
        stale = utcnow() - STALE_AFTER
        job = await session.scalar(
            select(ReviewJob)
            .where(or_(ReviewJob.status == "queued",
                       (ReviewJob.status == "running") & (ReviewJob.locked_at < stale)),
                   ReviewJob.attempts < MAX_ATTEMPTS)
            .order_by(ReviewJob.id).limit(1).with_for_update(skip_locked=True)
        )
        if job is None:
            return None
        job.status = "running"
        job.attempts += 1
        job.locked_at = utcnow()
        job.started_at = job.started_at or job.locked_at
        await session.commit()
        return job.id


async def process(job_id: int) -> None:
    async with SessionLocal() as session:
        job = await session.get(ReviewJob, job_id)
        try:
            await run_ai_lanes(session, job)
        except Exception as e:
            log.exception("review job %s failed", job_id)
            await session.rollback()
            job = await session.get(ReviewJob, job_id)
            job.error = f"{type(e).__name__}: {e}"[:1000]
            job.status = "failed" if job.attempts >= MAX_ATTEMPTS else "queued"
            await session.commit()


async def run_once() -> bool:
    job_id = await claim_job()
    if job_id is None:
        return False
    await process(job_id)
    return True


async def drain() -> int:
    """Process every queued job now (tests, seeding, eval)."""
    n = 0
    while await run_once():
        n += 1
    return n


async def loop(concurrency: int = 2) -> None:
    from app.seed.sandbox import housekeeping

    tasks: set[asyncio.Task] = set()
    last_housekeeping = 0.0

    while True:
        try:
            while len(tasks) < concurrency:  # claim only as many jobs as we can run
                job_id = await claim_job()
                if job_id is None:
                    break
                t = asyncio.create_task(process(job_id))
                tasks.add(t)
                t.add_done_callback(lambda done: (tasks.discard(done), wake()))
                await asyncio.sleep(0)
            now = asyncio.get_running_loop().time()
            if now - last_housekeeping > 60:
                last_housekeeping = now
                await housekeeping()
        except Exception:
            log.exception("worker loop error")
        _wake.clear()
        try:
            await asyncio.wait_for(_wake.wait(), timeout=1.0)
        except asyncio.TimeoutError:
            pass


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    get_settings()
    asyncio.run(loop())
