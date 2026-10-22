"""Local embeddings: fastembed bge-small-en-v1.5 (ONNX, 384-d). No text leaves the container.

If fastembed is not installed (lean dev setups, CI) a hashed bag-of-words embedding keeps the vector path working.
"""
import hashlib
import logging
import math
import re
from functools import lru_cache

from app.config import get_settings
from app.models import EMBED_DIM

log = logging.getLogger("countersign.embeddings")
_cache: dict[str, list[float]] = {}


@lru_cache(maxsize=1)
def _model():
    s = get_settings()
    if s.embeddings == "hash":
        return None
    try:
        from fastembed import TextEmbedding

        return TextEmbedding(model_name=s.embedding_model)
    except Exception as e:
        if s.embeddings == "fastembed":
            raise
        log.warning("fastembed unavailable (%s); using hashed embeddings", e)
        return None


def engine_name() -> str:
    return f"fastembed {get_settings().embedding_model} (local)" if _model() else "hashed bag-of-words (local fallback)"


def _hash_embed(text: str) -> list[float]:
    vec = [0.0] * EMBED_DIM
    tokens = re.findall(r"[a-z0-9%]+", text.lower())
    grams = tokens + [f"{a} {b}" for a, b in zip(tokens, tokens[1:], strict=False)]
    for g in grams:
        h = int.from_bytes(hashlib.md5(g.encode()).digest()[:8], "big")
        vec[h % EMBED_DIM] += 1.0 if (h >> 32) & 1 else -1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def embed(texts: list[str]) -> list[list[float]]:
    missing = [t for t in dict.fromkeys(texts) if t not in _cache]
    if missing:
        model = _model()
        if model is None:
            vectors = [_hash_embed(t) for t in missing]
        else:
            vectors = [list(map(float, v)) for v in model.embed(missing)]
        _cache.update(zip(missing, vectors, strict=False))
    return [_cache[t] for t in texts]


def warm() -> None:
    embed(["warm up"])
