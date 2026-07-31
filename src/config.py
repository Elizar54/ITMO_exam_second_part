"""Application settings for P0."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralized application configuration."""

    openrouter_api_key: str = ""
    openrouter_endpoint: str = "https://openrouter.ai/api/v1/chat/completions"
    openrouter_model: str = ""
    openrouter_timeout_seconds: int = Field(default=15, ge=1)
    openrouter_max_tokens: int = Field(default=500, ge=1)
    openrouter_temperature: float = Field(default=0.0, ge=0.0, le=1.0)
    openrouter_prompt_cost_per_1k: float = Field(default=0.0, ge=0.0)
    openrouter_completion_cost_per_1k: float = Field(default=0.0, ge=0.0)

    retrieval_top_k: int = Field(default=3, ge=1)
    retrieval_score_threshold: float = Field(default=0.60, ge=0.0, le=1.0)
    retrieval_margin_threshold: float = Field(default=0.03, ge=0.0, le=1.0)

    template_score_threshold: float = Field(default=0.72, ge=0.0, le=1.0)
    template_margin_threshold: float = Field(default=0.05, ge=0.0, le=1.0)

    scope_positive_threshold: float = Field(default=0.65, ge=0.0, le=1.0)
    scope_negative_threshold: float = Field(default=0.65, ge=0.0, le=1.0)
    scope_margin_threshold: float = Field(default=0.08, ge=0.0, le=1.0)

    primary_audit_path: Path = Path("runtime/audit.db")
    backup_audit_path: Path = Path("runtime/backup/audit_backup.jsonl")
    chroma_path: Path = Path("runtime/chroma")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
    )


settings = Settings()
