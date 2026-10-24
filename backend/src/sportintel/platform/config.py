"""Единственное место чтения env (CONV §2)."""

import os
import sys
from functools import lru_cache
from typing import Annotated, Literal, Self

import structlog
from pydantic import Field, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

Env = Literal["local", "ci", "e2e", "staging", "production"]
Csv = Annotated[list[str], NoDecode]

_DEV_LOGIN_ENVS = {"local", "e2e"}
_FAKE_OIDC_ENVS = {"local", "ci", "e2e"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    env: Env
    version: str = "dev"
    database_url: str
    database_url_migrator: str | None = None
    db_pool_size: int = Field(default=10, ge=1, le=50)
    app_base_url: str

    oidc_issuer: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: SecretStr | None = None
    oidc_allowed_domains: Csv = Field(default_factory=list)
    bootstrap_admin_email: str | None = None
    # Пароль первого admin (вход по паролю): создаётся при старте web, пока admin нет.
    initial_admin_password: SecretStr | None = Field(default=None, min_length=10)
    dev_login_enabled: bool = False

    # ADR-004: где выполняются шаги llm; none — LM нет, шаги работают по правилам
    ai_provider: Literal["none", "ollama", "fake", "anthropic"] = "none"
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-haiku-5-5"
    embeddings_provider: Literal["none", "ollama", "fake", "voyage"] = "none"
    voyage_api_key: SecretStr | None = None
    ai_record: bool = False
    ollama_url: str = "http://localhost:11434"
    ollama_timeout_s: int = Field(default=180, ge=1, le=3600)
    ollama_concurrency: int = Field(default=1, ge=1, le=16)

    sentry_dsn: SecretStr | None = None
    alert_telegram_bot_token: SecretStr | None = None
    alert_telegram_chat_id: str | None = None
    telegram_bot_token: SecretStr | None = (
        None  # бот публикации в каналы (docs/TELEGRAM_BOT_SETUP.md)
    )

    fetch_user_agent: str | None = None
    worker_concurrency: int = 4
    worker_interactive_concurrency: int = 2
    worker_fetch_concurrency: int = 4

    log_level: str = "INFO"
    log_format: Literal["json", "console"] | None = None
    safe_fetch_allow_hosts: Csv = Field(default_factory=list)
    safe_fetch_allow_fake_ip: bool = False
    static_dir: str = "/app/static"
    port: int = 8000
    csp_mode: Literal["report-only", "enforce"] = "report-only"

    @field_validator("oidc_allowed_domains", "safe_fetch_allow_hosts", mode="before")
    @classmethod
    def _split_csv(cls, v: object) -> object:
        if isinstance(v, str):
            return [p.strip() for p in v.split(",") if p.strip()]
        return v

    @field_validator("database_url", "database_url_migrator")
    @classmethod
    def _psycopg_url(cls, v: str | None) -> str | None:
        if v is not None and not v.startswith("postgresql+psycopg://"):
            raise ValueError("must start with postgresql+psycopg://")
        return v

    @property
    def oidc_enabled(self) -> bool:
        """Вход через IdP: в local/ci/e2e — фейковый IdP, иначе — только если OIDC_* заданы."""
        return self.env in _FAKE_OIDC_ENVS or bool(self.oidc_issuer)

    @model_validator(mode="after")
    def _cross_field(self) -> Self:
        oidc = ("oidc_issuer", "oidc_client_id", "oidc_client_secret")
        given = [n for n in oidc if getattr(self, n)]
        if given and len(given) < len(oidc):
            # Половина настроек — почти всегда опечатка; без OIDC вовсе — вход по паролю.
            missing = [n.upper() for n in oidc if n not in given]
            raise ValueError(f"OIDC is partially configured, missing: {', '.join(missing)}")
        if self.dev_login_enabled and self.env not in _DEV_LOGIN_ENVS:
            raise ValueError("DEV_LOGIN_ENABLED is allowed only for ENV in {local, e2e}")
        if self.ai_provider == "anthropic" and not self.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is required when AI_PROVIDER=anthropic")
        if self.embeddings_provider == "voyage" and not self.voyage_api_key:
            raise ValueError("VOYAGE_API_KEY is required when EMBEDDINGS_PROVIDER=voyage")
        if self.safe_fetch_allow_hosts and self.env != "e2e":
            raise ValueError("SAFE_FETCH_ALLOW_HOSTS is allowed only for ENV=e2e")
        if self.safe_fetch_allow_fake_ip and self.env != "local":
            raise ValueError("SAFE_FETCH_ALLOW_FAKE_IP is allowed only for ENV=local")

        if self.database_url_migrator is None:
            self.database_url_migrator = self.database_url
        if self.log_format is None:
            self.log_format = "console" if self.env == "local" else "json"
        if self.fetch_user_agent is None:
            self.fetch_user_agent = f"SportIntelBot/1.0 (+{self.app_base_url}/bot)"
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # поля приходят из env


def enabled_flags() -> list[str]:
    """Имена FLAG_* из env со значением true; разбор и KNOWN_FLAGS — platform/flags.py."""
    return sorted(
        k
        for k, v in os.environ.items()
        if k.startswith("FLAG_") and v.strip().lower() in {"1", "true", "yes", "on"}
    )


def load_settings_or_exit() -> Settings:
    try:
        return get_settings()
    except ValidationError as e:
        fields = sorted({str(err["loc"][0]).upper() for err in e.errors() if err["loc"]})
        # ошибки кросс-полевых правил приходят без loc — сообщение без значений секретов
        rules = [err["msg"] for err in e.errors() if not err["loc"]]
        structlog.get_logger("sportintel.config").error(
            "config.invalid", fields=fields, rules=rules
        )
        sys.exit(1)
