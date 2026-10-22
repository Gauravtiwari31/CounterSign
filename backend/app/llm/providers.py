"""Provider clients. Each returns raw JSON text; validation happens in the adapter."""
import asyncio

import httpx

from app.config import get_settings


class ProviderError(Exception):
    pass


class GeminiProvider:
    """Plain REST over httpx: the SDK retried 503s internally and ignored our timeout."""

    name = "gemini"
    URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    RETRY_STATUS = {429, 500, 503}

    def __init__(self, model: str, api_key: str):
        self.model = model
        self._client = httpx.AsyncClient(headers={"x-goog-api-key": api_key},
                                         timeout=get_settings().llm_timeout_s)

    async def complete_json(self, system: str, user: str) -> str:
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.0},
        }
        for attempt in range(2):  # one quick retry on overload, then the adapter moves to the fallback
            try:
                r = await self._client.post(self.URL.format(model=self.model), json=body)
            except httpx.HTTPError as e:
                raise ProviderError(f"gemini {self.model}: {type(e).__name__}: {e}") from e
            if r.status_code in self.RETRY_STATUS and attempt == 0:
                await asyncio.sleep(1.5)
                continue
            if r.status_code != 200:
                raise ProviderError(f"gemini {self.model}: HTTP {r.status_code}: {r.text[:200]}")
            break
        parts = (r.json().get("candidates") or [{}])[0].get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        if not text:
            raise ProviderError(f"gemini {self.model}: empty response")
        return text


class GroqProvider:
    name = "groq"

    def __init__(self, model: str, api_key: str):
        from openai import AsyncOpenAI

        self.model = model
        self._client = AsyncOpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1",
                                   timeout=get_settings().llm_timeout_s, max_retries=0)

    async def complete_json(self, system: str, user: str) -> str:
        try:
            resp = await self._client.chat.completions.create(
                model=self.model, temperature=0.0, response_format={"type": "json_object"},
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            )
        except Exception as e:
            raise ProviderError(f"groq: {type(e).__name__}: {e}") from e
        content = resp.choices[0].message.content
        if not content:
            raise ProviderError("groq: empty response")
        return content


def build_providers() -> list:
    s = get_settings()
    out = []
    for provider, model in ((s.llm_primary_provider, s.llm_primary_model), (s.llm_fallback_provider, s.llm_fallback_model)):
        if provider == "gemini" and s.gemini_api_key:
            out.append(GeminiProvider(model, s.gemini_api_key))
        elif provider == "groq" and s.groq_api_key:
            out.append(GroqProvider(model, s.groq_api_key))
    return out
