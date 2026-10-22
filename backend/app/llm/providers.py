"""Provider clients. Each returns raw JSON text; validation happens in the adapter."""
import asyncio

from app.config import get_settings


class ProviderError(Exception):
    pass


class GeminiProvider:
    name = "gemini"

    def __init__(self, model: str, api_key: str):
        from google import genai

        self.model = model
        self._client = genai.Client(api_key=api_key)

    async def complete_json(self, system: str, user: str) -> str:
        from google.genai import types

        cfg = types.GenerateContentConfig(
            system_instruction=system, response_mime_type="application/json", temperature=0.0,
        )
        try:
            resp = await asyncio.wait_for(
                self._client.aio.models.generate_content(model=self.model, contents=user, config=cfg),
                timeout=get_settings().llm_timeout_s,
            )
        except Exception as e:  # network, quota, timeout
            raise ProviderError(f"gemini: {type(e).__name__}: {e}") from e
        if not resp.text:
            raise ProviderError("gemini: empty response")
        return resp.text


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
