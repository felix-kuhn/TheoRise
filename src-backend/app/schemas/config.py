"""Runtime model configuration shared by the API and the gateway."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import AnyHttpUrl, BaseModel, Field, SecretStr

DEFAULT_BASE_URL = "http://127.0.0.1:8000/v1"


class ModelRoleConfig(BaseModel):
    """OpenAI-compatible settings for one model role."""

    base_url: AnyHttpUrl = Field(default_factory=lambda: AnyHttpUrl(DEFAULT_BASE_URL))
    model: str = ""
    api_key: SecretStr | None = None
    system_instructions: str = ""
    temperature: float = 0.0
    max_tokens: int | None = None
    timeout_s: float = 120.0
    extra_headers: dict[str, str] = Field(default_factory=dict)
    extra_body: dict[str, Any] = Field(default_factory=dict)
    supports_json_schema: bool | None = None


class EmbeddingConfig(ModelRoleConfig):
    """Embedding-specific settings."""

    dimensions: int | None = None
    query_prefix: str = ""
    document_prefix: str = ""
    batch_size: int = 32


class RerankConfig(BaseModel):
    """Reranking mode and endpoint settings."""

    mode: Literal["none", "endpoint", "llm"] = "none"
    base_url: AnyHttpUrl | None = None
    model: str | None = None
    api_key: SecretStr | None = None
    top_n: int = 10


class AppConfig(BaseModel):
    """Complete runtime configuration for the research assistant."""

    chat: ModelRoleConfig = Field(default_factory=ModelRoleConfig)
    extraction: ModelRoleConfig = Field(default_factory=ModelRoleConfig)
    linking: ModelRoleConfig = Field(default_factory=ModelRoleConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    rerank: RerankConfig = Field(default_factory=RerankConfig)
    concurrency: int = 4
    token_budget_per_job: int | None = None


ROLE_NAMES = ("chat", "extraction", "linking", "embedding", "rerank")


def role_config(config: AppConfig, role: str) -> ModelRoleConfig | RerankConfig:
    """Return the configuration object for a role name."""
    if role not in ROLE_NAMES:
        raise KeyError(role)
    return getattr(config, role)


def role_api_key(config: AppConfig, role: str) -> SecretStr | None:
    return getattr(config, role).api_key
