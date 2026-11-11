"""Application settings. Secrets are SecretStr and never appear in repr, str or logs."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# apps/api/src/marginos/core/config.py -> repository root is five levels up.
REPO_ROOT = Path(__file__).resolve().parents[5]

Provider = Literal["openai", "groq", "gemini"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # App
    app_env: Literal["development", "production"] = "development"
    app_base_url: str = "http://localhost:8000"
    web_base_url: str = "http://localhost:5173"
    app_secret_key: SecretStr = SecretStr("")

    # Database
    database_url: str = "postgresql+psycopg://marginos:marginos@localhost:5433/marginos"

    # PayPal
    paypal_env: Literal["sandbox", "live"] = "sandbox"
    paypal_api_base: str = "https://api-m.sandbox.paypal.com"
    paypal_client_id: str = ""
    paypal_client_secret: SecretStr = SecretStr("")
    paypal_webhook_id: str = ""
    paypal_webhook_url: str = ""
    paypal_merchant_email: str = ""
    paypal_webhook_skip_verify: bool = False
    paypal_buyer_us_email: str = ""
    paypal_buyer_us_password: SecretStr = SecretStr("")
    paypal_buyer_eu_email: str = ""
    paypal_buyer_eu_password: SecretStr = SecretStr("")

    # Channel3
    channel3_api_key: SecretStr = SecretStr("")
    channel3_api_base: str = "https://api.trychannel3.com"

    # LLM
    llm_primary_provider: Provider = "openai"
    llm_fallback_provider: Provider | None = "gemini"
    llm_base_url_override: str = ""
    openai_api_key: SecretStr = SecretStr("")
    openai_model: str = ""
    groq_api_key: SecretStr = SecretStr("")
    groq_model: str = ""
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = ""

    @model_validator(mode="after")
    def _production_guards(self) -> Settings:
        if self.app_env == "production" and self.paypal_webhook_skip_verify:
            raise ValueError("PAYPAL_WEBHOOK_SKIP_VERIFY cannot be enabled when APP_ENV=production")
        return self

    def missing_required(self) -> list[str]:
        """Names of secrets that must be present for the integrations to work."""
        required = {
            "PAYPAL_CLIENT_ID": self.paypal_client_id,
            "PAYPAL_CLIENT_SECRET": self.paypal_client_secret.get_secret_value(),
            "PAYPAL_WEBHOOK_ID": self.paypal_webhook_id,
            "CHANNEL3_API_KEY": self.channel3_api_key.get_secret_value(),
        }
        return [name for name, value in required.items() if not value]


@lru_cache
def get_settings() -> Settings:
    return Settings()
