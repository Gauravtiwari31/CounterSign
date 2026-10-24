import httpx
import pytest

from app.llm import providers
from app.llm.providers import GeminiProvider, ProviderError, quota_info

DAILY = ('{"error":{"code":429,"message":"Quota exceeded ... Please retry in 1h18m54.79s.","details":[{"violations":'
         '[{"quotaId":"GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}]}}')
PER_MINUTE = ('{"error":{"code":429,"details":[{"violations":[{"quotaId":"GenerateRequestsPerMinutePerProjectPerModel"}]},'
              '{"@type":"type.googleapis.com/google.rpc.RetryInfo","retryDelay":"3s"}]}}')
OK = '{"candidates":[{"content":{"parts":[{"text":"{}"}]}}]}'


def test_quota_info_reads_daily_and_delay():
    daily, delay = quota_info(DAILY)
    assert daily and delay == pytest.approx(3600 + 18 * 60 + 54.79)
    assert quota_info(PER_MINUTE) == (False, 3.0)
    assert quota_info("{}") == (False, None)


def _provider(responses: list[tuple[int, str]]) -> tuple[GeminiProvider, list]:
    calls = []

    def handler(request):
        calls.append(request)
        code, body = responses[min(len(calls), len(responses)) - 1]
        return httpx.Response(code, text=body)

    p = GeminiProvider("m", "k")
    p._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return p, calls


async def test_daily_quota_marks_provider_unavailable_without_retrying():
    p, calls = _provider([(429, DAILY)])
    with pytest.raises(ProviderError, match="daily quota"):
        await p.complete_json("s", "u")
    assert len(calls) == 1 and not p.available()
    with pytest.raises(ProviderError):  # later calls fail fast, no request sent
        await p.complete_json("s", "u")
    assert len(calls) == 1


async def test_per_minute_limit_waits_then_retries(monkeypatch):
    waits = []

    async def fake_sleep(s):
        waits.append(s)

    monkeypatch.setattr(providers.asyncio, "sleep", fake_sleep)
    p, calls = _provider([(429, PER_MINUTE), (200, OK)])
    assert await p.complete_json("s", "u") == "{}"
    assert waits == [3.0] and len(calls) == 2 and p.available()
