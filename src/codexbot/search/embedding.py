"""Lazy local embedding provider for search indexing and retrieval."""

from __future__ import annotations

import os
from dataclasses import dataclass
from threading import Lock
from typing import Any, Protocol


DEFAULT_EMBEDDING_MODEL_ID = "Qwen/Qwen3-Embedding-0.6B"
DEFAULT_EMBEDDING_DIMENSION = 1024
DEFAULT_EMBEDDING_BATCH_SIZE = 16
QUERY_INSTRUCTION = (
    "Represent this Codi Codex/Claude session search query for retrieving "
    "relevant active-session transcript chunks: "
)


class EmbeddingProvider(Protocol):
    """Embedding provider boundary used by worker/query code and tests."""

    model_id: str
    vector_dimension: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed transcript chunks."""
        ...

    def embed_query(self, text: str) -> list[float]:
        """Embed a user search query."""
        ...


@dataclass(frozen=True)
class EmbeddingConfig:
    """Environment-derived local embedding configuration."""

    model_id: str
    vector_dimension: int
    batch_size: int
    local_files_only: bool
    device: str | None = None


def _normalize_device(raw: str | None) -> str | None:
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        return None
    if value.lower() == "auto":
        return None
    if value.isdecimal():
        return f"cuda:{value}"
    return value


def embedding_config_from_env() -> EmbeddingConfig:
    """Read embedding config without importing the model stack."""
    # The default is cpu: PyTorch MPS on Apple Silicon has hung the worker
    # mid-load on Qwen3-Embedding. CPU is slower but reliable for the
    # one-shot backfill. Set "auto" to delegate to SentenceTransformer's
    # built-in selection, or "mps"/"cuda" explicitly.
    return EmbeddingConfig(
        model_id=os.getenv("CODEXBOT_SEARCH_MODEL_ID", DEFAULT_EMBEDDING_MODEL_ID),
        vector_dimension=int(
            os.getenv("CODEXBOT_SEARCH_VECTOR_DIM", str(DEFAULT_EMBEDDING_DIMENSION))
        ),
        batch_size=int(
            os.getenv("CODEXBOT_SEARCH_BATCH_SIZE", str(DEFAULT_EMBEDDING_BATCH_SIZE))
        ),
        local_files_only=os.getenv("CODEXBOT_SEARCH_LOCAL_FILES_ONLY", "false").lower()
        in {"1", "true", "yes"},
        device=_normalize_device(os.getenv("CODEXBOT_SEARCH_DEVICE", "cpu")),
    )


class SentenceTransformerEmbeddingProvider:
    """Local SentenceTransformer-backed embedding provider."""

    def __init__(self, config: EmbeddingConfig | None = None) -> None:
        self.config = config or embedding_config_from_env()
        self.model_id = self.config.model_id
        self.vector_dimension = self.config.vector_dimension
        self._model: object | None = None
        self._model_lock = Lock()

    def _load_model(self) -> object:
        if self._model is None:
            with self._model_lock:
                if self._model is None:
                    from sentence_transformers import SentenceTransformer

                    kwargs: dict[str, Any] = {}
                    if self.config.local_files_only:
                        kwargs["local_files_only"] = True
                    if self.config.device:
                        kwargs["device"] = self.config.device
                    # Float16 halves resident RAM for Qwen3-Embedding-0.6B and
                    # keeps cosine similarity close enough for the existing
                    # float32 LanceDB index.
                    kwargs["model_kwargs"] = {"torch_dtype": "float16"}
                    self._model = SentenceTransformer(self.model_id, **kwargs)
        return self._model

    def _encode(self, texts: list[str]) -> list[list[float]]:
        model = self._load_model()
        encoded = model.encode(  # type: ignore[attr-defined]
            texts,
            batch_size=self.config.batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        vectors: list[list[float]] = []
        for vector in encoded:
            values = [float(value) for value in vector]
            if len(values) > self.vector_dimension:
                values = values[: self.vector_dimension]
            vectors.append(values)
        return vectors

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._encode(texts)

    def embed_query(self, text: str) -> list[float]:
        [vector] = self._encode([f"{QUERY_INSTRUCTION}{text}"])
        return vector


_provider_override: EmbeddingProvider | None = None
_provider_cache: dict[EmbeddingConfig, EmbeddingProvider] = {}
_provider_cache_lock = Lock()


def clear_embedding_provider_cache() -> None:
    """Drop cached model providers.

    Tests use this to isolate env-var changes. Production keeps one provider
    hot so each search request does not reload the SentenceTransformer model.
    """
    with _provider_cache_lock:
        _provider_cache.clear()


def set_embedding_provider_for_tests(provider: EmbeddingProvider | None) -> None:
    """Inject a deterministic provider for unit tests."""
    global _provider_override
    _provider_override = provider
    clear_embedding_provider_cache()


def get_embedding_provider() -> EmbeddingProvider:
    """Return the configured local embedding provider.

    The SentenceTransformer-backed provider holds a ~1GB Qwen3 model in
    memory once loaded; creating a fresh provider per query forced a
    cold reload (~60s on CPU) every time. We cache one instance per
    process and reuse it across requests — first query still pays the
    load, subsequent queries are millisecond-level.
    """
    if _provider_override is not None:
        return _provider_override
    config = embedding_config_from_env()
    with _provider_cache_lock:
        provider = _provider_cache.get(config)
        if provider is None:
            provider = SentenceTransformerEmbeddingProvider(config)
            _provider_cache[config] = provider
        return provider


def warm_embedding_provider() -> None:
    """Load and warm the configured provider for future query latency."""
    get_embedding_provider().embed_query("warm up Codi local session search")


__all__ = [
    "DEFAULT_EMBEDDING_DIMENSION",
    "DEFAULT_EMBEDDING_MODEL_ID",
    "EmbeddingConfig",
    "EmbeddingProvider",
    "QUERY_INSTRUCTION",
    "SentenceTransformerEmbeddingProvider",
    "clear_embedding_provider_cache",
    "embedding_config_from_env",
    "get_embedding_provider",
    "set_embedding_provider_for_tests",
    "warm_embedding_provider",
]
