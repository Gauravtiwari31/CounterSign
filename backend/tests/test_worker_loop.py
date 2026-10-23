import asyncio

from app import worker
from app.seed import sandbox


async def test_slow_housekeeping_does_not_block_job_claims(monkeypatch):
    queue = [1]
    processed = []

    async def slow_housekeeping():
        await asyncio.sleep(30)  # a pool refill over a slow database link

    async def claim_job():
        return queue.pop() if queue else None

    async def process(job_id):
        processed.append(job_id)

    monkeypatch.setattr(sandbox, "housekeeping", slow_housekeeping)
    monkeypatch.setattr(worker, "claim_job", claim_job)
    monkeypatch.setattr(worker, "process", process)

    loop_task = asyncio.create_task(worker.loop())
    await asyncio.sleep(0.1)
    queue.append(2)  # submitted while housekeeping is still running
    worker.wake()
    await asyncio.sleep(0.2)
    loop_task.cancel()
    await asyncio.gather(loop_task, return_exceptions=True)

    assert processed == [1, 2]
