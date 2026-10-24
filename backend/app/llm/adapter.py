"""One entry point for every LLM call: cache -> primary (+1 repair) -> fallback (+1 repair) -> LLMUnavailable.

Callers fall back to deterministic behaviour on LLMUnavailable; a lane never silently passes.
"""
import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import TypeVar

from pydantic import BaseModel, ValidationError
from sqlalchemy.dialects.postgresql import insert

from app.config import get_settings
from app.db import SessionLocal
from app.llm.providers import ProviderError, build_providers
from app.models import LlmCache, utcnow

log = logging.getLogger("countersign.llm")
T = TypeVar("T", bound=BaseModel)


class LLMUnavailable(Exception):
    pass


@dataclass
class CallMeta:
    provider: str
    model: str
    cached: bool
    prompt_version: str


@dataclass
class Stats:
    calls: int = 0
    cache_hits: int = 0
    failures: int = 0
    repairs: int = 0
    last_ok_provider: str | None = None
    last_error: str | None = None
    answered_by: dict = field(default_factory=dict)  # model -> live calls it answered


stats = Stats()
_sem: asyncio.Semaphore | None = None
_providers: list | None = None
# tests can install a fake provider list here
override_providers: list | None = None


def providers() -> list:
    global _providers
    if override_providers is not None:
        return override_providers
    if _providers is None:
        _providers = build_providers()
    return _providers


def configured() -> bool:
    return bool(providers())


def _semaphore() -> asyncio.Semaphore:
    global _sem
    if _sem is None:
        _sem = asyncio.Semaphore(get_settings().llm_concurrency)
    return _sem


def cache_key(prompt_version: str, model: str, user: str, cache_extra: str) -> str:
    return hashlib.sha256(f"{prompt_version}|{model}|{user}|{cache_extra}".encode()).hexdigest()


def _schema_hint(schema: type[BaseModel]) -> str:
    return json.dumps(schema.model_json_schema(), separators=(",", ":"))


def _parse(raw: str, schema: type[T]) -> T:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`").removeprefix("json").strip()
    return schema.model_validate_json(raw)


async def _cache_get(key: str) -> dict | None:
    async with SessionLocal() as s:
        row = await s.get(LlmCache, key)
        return row.response if row else None


async def _cache_put(key: str, provider: str, model: str, prompt_version: str, response: dict) -> None:
    async with SessionLocal() as s:
        await s.execute(insert(LlmCache).values(
            key=key, provider=provider, model=model, prompt_version=prompt_version, response=response,
            created_at=utcnow(),
        ).on_conflict_do_nothing())
        await s.commit()


async def generate_json(
    *, system: str, user: str, schema: type[T], prompt_version: str, cache_extra: str = "",
) -> tuple[T, CallMeta]:
    provs = providers()
    if not provs:
        raise LLMUnavailable("No LLM provider configured")
    system_full = (
        system + "\n\nRespond with a single JSON object that validates against this JSON Schema:\n" + _schema_hint(schema)
    )
    if get_settings().log_prompts:
        log.info("PROMPT %s\n%s", prompt_version, user)

    # any provider's cached answer beats spending quota on a live call
    for prov in provs:
        cached = await _cache_get(cache_key(prompt_version, prov.model, user, cache_extra))
        if cached is not None:
            try:
                obj = schema.model_validate(cached)
                stats.cache_hits += 1
                return obj, CallMeta(prov.name, prov.model, True, prompt_version)
            except ValidationError:
                pass

    errors = []
    for prov in provs:
        if not getattr(prov, "available", lambda: True)():
            errors.append(f"{prov.name} {prov.model}: daily quota used up")
            continue
        key = cache_key(prompt_version, prov.model, user, cache_extra)
        message = user
        for _attempt in range(2):  # first try + one repair
            try:
                async with _semaphore():
                    stats.calls += 1
                    raw = await prov.complete_json(system_full, message)
                obj = _parse(raw, schema)
                await _cache_put(key, prov.name, prov.model, prompt_version, obj.model_dump(mode="json"))
                stats.last_ok_provider = prov.name
                stats.answered_by[prov.model] = stats.answered_by.get(prov.model, 0) + 1
                return obj, CallMeta(prov.name, prov.model, False, prompt_version)
            except ValidationError as e:
                stats.repairs += 1
                errors.append(f"{prov.name}: schema: {e.errors()[:2]}")
                message = (
                    user + "\n\nYour previous reply did not match the schema. Errors: "
                    + json.dumps(e.errors()[:5], default=str) + "\nReturn only corrected JSON."
                )
            except (ProviderError, json.JSONDecodeError, ValueError) as e:
                errors.append(str(e))
                break
    stats.failures += 1
    stats.last_error = "; ".join(errors)[-500:]
    log.warning("LLM unavailable for %s: %s", prompt_version, stats.last_error)
    raise LLMUnavailable(stats.last_error)
