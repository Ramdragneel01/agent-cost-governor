"""Application configuration loaded from environment variables."""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for agent-cost-governor.

    Variables are prefixed with ``ACG_`` and read from the environment
    or a local ``.env`` file.
    """

    model_config = SettingsConfigDict(
        env_prefix="ACG_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    upstream_base_url: str = Field(default="https://api.openai.com")
    upstream_api_key: str = Field(default="")

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8090)
    log_level: str = Field(default="INFO")

    # Path to the YAML policy file (budgets, model rules).
    policy_path: str = Field(default="policy.yaml")

    # Tenant identification: which header carries the tenant id.
    tenant_header: str = Field(default="x-acg-tenant")
    default_tenant: str = Field(default="default")

    # Webhook to fire when a tenant crosses 80% / 100% of budget.
    alert_webhook_url: str = Field(default="")

    service_name: str = Field(default="agent-cost-governor")


@lru_cache
def get_settings() -> Settings:
    return Settings()
