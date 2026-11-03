from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import (
    DEFAULT_DATABASE_URL,
    Environment,
    Settings,
)

ENV_KEYS = (
    "APP_NAME",
    "APP_VERSION",
    "ENVIRONMENT",
    "DEBUG",
    "API_V1_PREFIX",
    "DATABASE_URL",
    "CORS_ORIGINS",
    "CORS_ALLOW_CREDENTIALS",
    "LOG_LEVEL",
    "DB_ECHO",
    "DB_REQUIRE_TLS",
)

PRODUCTION_DATABASE_URL = (
    "postgresql+asyncpg://realuser:realpass@db.example.com:5432/"
    "fieldops?ssl=verify-full"
)


def production_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "environment": "production",
        "debug": False,
        "database_url": PRODUCTION_DATABASE_URL,
        "cors_origins": "https://app.example.com",
    }
    values.update(overrides)
    return Settings(**values)


def test_default_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)

    settings = Settings(_env_file=None)

    assert settings.app_name == "FieldOps AI"
    assert settings.environment is Environment.DEVELOPMENT
    assert settings.debug is False
    assert settings.api_v1_prefix == "/api/v1"
    assert settings.database_url == DEFAULT_DATABASE_URL
    assert settings.allowed_origins == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    assert settings.cors_allow_credentials is True
    assert settings.log_level == "INFO"
    assert settings.db_require_tls is True


def test_database_url_is_normalized_to_asyncpg() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql://user:pass@localhost:5432/fieldops",
    )

    assert settings.database_url == (
        "postgresql+asyncpg://user:pass@localhost:5432/fieldops"
    )


def test_database_url_port_is_optional() -> None:
    settings = Settings(
        _env_file=None,
        database_url=(
            "postgresql+asyncpg://user:pass@localhost/fieldops"
        ),
    )

    assert settings.database_url == (
        "postgresql+asyncpg://user:pass@localhost/fieldops"
    )


def test_non_postgres_database_url_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url="sqlite+aiosqlite:///test.db")


def test_api_prefix_is_normalized() -> None:
    settings = Settings(_env_file=None, api_v1_prefix="api/v1/")

    assert settings.api_v1_prefix == "/api/v1"


def test_cors_origins_are_parsed_from_comma_separated_value() -> None:
    settings = Settings(
        _env_file=None,
        cors_origins="https://app.example.com, https://admin.example.com ,",
    )

    assert settings.allowed_origins == [
        "https://app.example.com",
        "https://admin.example.com",
    ]


def test_invalid_log_level_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, log_level="verbose")


def test_production_rejects_debug_mode() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            environment="production",
            debug=True,
            database_url=(
                "postgresql+asyncpg://realuser:realpass@db.example.com/prod"
            ),
            cors_origins="https://app.example.com",
        )


def test_production_rejects_default_database_url() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            environment="production",
            debug=False,
            database_url=DEFAULT_DATABASE_URL,
            cors_origins="https://app.example.com",
        )


def test_production_rejects_placeholder_credentials() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            environment="production",
            debug=False,
            database_url=(
                "postgresql+asyncpg://fieldops:fieldops@db.example.com/prod"
            ),
            cors_origins="https://app.example.com",
        )


def test_valid_production_settings_are_accepted() -> None:
    settings = production_settings()

    assert settings.environment is Environment.PRODUCTION
    assert settings.is_production is True


def test_production_rejects_wildcard_cors_with_credentials() -> None:
    with pytest.raises(ValidationError):
        production_settings(cors_origins="*")


def test_production_allows_wildcard_cors_without_credentials() -> None:
    settings = production_settings(
        cors_origins="*",
        cors_allow_credentials=False,
    )

    assert settings.allowed_origins == ["*"]


def test_production_rejects_db_echo() -> None:
    with pytest.raises(ValidationError):
        production_settings(db_echo=True)


@pytest.mark.parametrize(
    "database_url",
    [
        "postgresql+asyncpg://realuser:realpass@db.example.com:5432/fieldops",
        (
            "postgresql+asyncpg://realuser:realpass@db.example.com:5432/"
            "fieldops?ssl=disable"
        ),
        (
            "postgresql+asyncpg://realuser:realpass@db.example.com:5432/"
            "fieldops?ssl=prefer"
        ),
        (
            "postgresql+asyncpg://realuser:realpass@db.example.com:5432/"
            "fieldops?ssl=allow"
        ),
    ],
)
def test_production_rejects_missing_or_insecure_tls(
    database_url: str,
) -> None:
    with pytest.raises(ValidationError):
        production_settings(database_url=database_url)


@pytest.mark.parametrize(
    "ssl_mode",
    ["require", "verify-ca", "verify-full"],
)
def test_production_accepts_secure_tls_modes(ssl_mode: str) -> None:
    settings = production_settings(
        database_url=(
            "postgresql+asyncpg://realuser:realpass@db.example.com:5432/"
            f"fieldops?ssl={ssl_mode}"
        )
    )

    assert settings.is_production is True


def test_production_allows_explicit_tls_opt_out() -> None:
    settings = production_settings(
        database_url=(
            "postgresql+asyncpg://realuser:realpass@db.example.com:5432/"
            "fieldops"
        ),
        db_require_tls=False,
    )

    assert settings.is_production is True


@pytest.mark.parametrize(
    "database_url",
    [
        (
            "postgresql+asyncpg://postgres:postgres@db.example.com:5432/"
            "fieldops?ssl=verify-full"
        ),
        (
            "postgresql+asyncpg://admin:admin@db.example.com:5432/"
            "fieldops?ssl=verify-full"
        ),
        (
            "postgresql+asyncpg://realuser:password@db.example.com:5432/"
            "fieldops?ssl=verify-full"
        ),
        (
            "postgresql+asyncpg://realuser:changeme@db.example.com:5432/"
            "fieldops?ssl=verify-full"
        ),
        (
            "postgresql+asyncpg://realuser:@db.example.com:5432/"
            "fieldops?ssl=verify-full"
        ),
        (
            "postgresql+asyncpg://realuser@db.example.com:5432/"
            "fieldops?ssl=verify-full"
        ),
        (
            "postgresql+asyncpg://:realpass@db.example.com:5432/"
            "fieldops?ssl=verify-full"
        ),
    ],
)
def test_production_rejects_empty_or_weak_credentials(
    database_url: str,
) -> None:
    with pytest.raises(ValidationError):
        production_settings(database_url=database_url)


@pytest.mark.parametrize(
    "database_url",
    [
        "postgresql+asyncpg://",
        "postgresql+asyncpg://user:pass@/fieldops",
        "postgresql+asyncpg://user:pass@localhost",
        "postgresql+asyncpg://user:pass@localhost:0/fieldops",
        "postgresql+asyncpg://user:pass@localhost:70000/fieldops",
        "postgresql+asyncpg://user:pass@localhost:notaport/fieldops",
    ],
)
def test_invalid_database_url_structure_is_rejected(
    database_url: str,
) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url=database_url)


def test_local_development_allows_non_tls_database_url() -> None:
    settings = Settings(
        _env_file=None,
        environment="development",
        database_url=DEFAULT_DATABASE_URL,
    )

    assert settings.database_url == DEFAULT_DATABASE_URL
