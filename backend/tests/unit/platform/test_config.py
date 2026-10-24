import pytest
from pydantic import ValidationError

from sportintel.platform.config import Settings, get_settings

BASE = {
    "env": "local",
    "database_url": "postgresql+psycopg://u:p@localhost/db",
    "app_base_url": "http://localhost:8000",
}
OIDC = {
    "oidc_issuer": "https://accounts.google.com",
    "oidc_client_id": "id",
    "oidc_client_secret": "s3cr3t",
}


def make(**overrides: object) -> Settings:
    return Settings(**{**BASE, **overrides})


def test_env_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENV", raising=False)
    with pytest.raises(ValidationError, match="env"):
        Settings(database_url=BASE["database_url"], app_base_url=BASE["app_base_url"])


def test_database_url_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError, match="database_url"):
        Settings(env="local", app_base_url=BASE["app_base_url"])


def test_database_url_must_use_psycopg() -> None:
    with pytest.raises(ValidationError, match="postgresql\\+psycopg"):
        make(database_url="postgresql://u:p@localhost/db")


@pytest.mark.parametrize("env", ["staging", "production"])
def test_oidc_optional_outside_dev(env: str) -> None:
    assert not make(env=env).oidc_enabled  # без OIDC_* — только вход по паролю
    assert make(env=env, **OIDC).oidc_enabled


def test_oidc_partial_config_rejected() -> None:
    with pytest.raises(ValidationError, match="OIDC_CLIENT_SECRET"):
        make(env="production", oidc_issuer="https://i", oidc_client_id="c")


def test_initial_admin_password_min_length() -> None:
    with pytest.raises(ValidationError, match="initial_admin_password"):
        make(initial_admin_password="short")


@pytest.mark.parametrize("env", ["local", "ci", "e2e"])
def test_oidc_optional_in_dev(env: str) -> None:
    assert make(env=env).oidc_enabled  # фейковый IdP


@pytest.mark.parametrize("env", ["ci", "staging", "production"])
def test_dev_login_forbidden_outside_local_e2e(env: str) -> None:
    with pytest.raises(ValidationError, match="DEV_LOGIN_ENABLED"):
        make(env=env, dev_login_enabled=True, **OIDC)


@pytest.mark.parametrize("env", ["local", "e2e"])
def test_dev_login_allowed_local_e2e(env: str) -> None:
    assert make(env=env, dev_login_enabled=True).dev_login_enabled


def test_anthropic_requires_key() -> None:
    with pytest.raises(ValidationError, match="ANTHROPIC_API_KEY"):
        make(ai_provider="anthropic")
    assert make(ai_provider="anthropic", anthropic_api_key="k").ai_provider == "anthropic"


def test_voyage_requires_key() -> None:
    with pytest.raises(ValidationError, match="VOYAGE_API_KEY"):
        make(embeddings_provider="voyage")


def test_safe_fetch_allow_hosts_only_e2e() -> None:
    with pytest.raises(ValidationError, match="SAFE_FETCH_ALLOW_HOSTS"):
        make(safe_fetch_allow_hosts="fake-source")
    assert make(env="e2e", safe_fetch_allow_hosts="a, b").safe_fetch_allow_hosts == ["a", "b"]


def test_safe_fetch_allow_fake_ip_only_local() -> None:
    assert make(safe_fetch_allow_fake_ip=True).safe_fetch_allow_fake_ip
    with pytest.raises(ValidationError, match="SAFE_FETCH_ALLOW_FAKE_IP"):
        make(env="e2e", safe_fetch_allow_fake_ip=True)


def test_derived_defaults() -> None:
    s = make()
    assert s.database_url_migrator == s.database_url
    assert s.log_format == "console"
    assert s.fetch_user_agent == "SportIntelBot/1.0 (+http://localhost:8000/bot)"
    assert make(env="ci").log_format == "json"


def test_secrets_hidden_in_repr() -> None:
    s = make(env="staging", **OIDC)
    assert "s3cr3t" not in repr(s)


def test_reads_env_and_csv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "local")
    monkeypatch.setenv("DATABASE_URL", BASE["database_url"])
    monkeypatch.setenv("APP_BASE_URL", BASE["app_base_url"])
    monkeypatch.setenv("OIDC_ALLOWED_DOMAINS", "example.com,corp.example.com")
    s = get_settings()
    assert s.oidc_allowed_domains == ["example.com", "corp.example.com"]
    assert get_settings() is s


def test_ai_provider_defaults_to_none_and_accepts_ollama() -> None:
    s = make()
    assert (s.ai_provider, s.embeddings_provider, s.ollama_concurrency) == ("none", "none", 1)
    assert make(ai_provider="ollama", embeddings_provider="ollama").ai_provider == "ollama"
