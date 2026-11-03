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
    "LOG_LEVEL",
)


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
    assert settings.log_level == "INFO"


def test_database_url_is_normalized_to_asyncpg() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql://user:pass@localhost:5432/fieldops",
    )

    assert settings.database_url == (
        "postgresql+asyncpg://user:pass@localhost:5432/fieldops"
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
    settings = Settings(
        _env_file=None,
        environment="production",
        debug=False,
        database_url=(
            "postgresql+asyncpg://realuser:realpass@db.example.com/prod"
        ),
        cors_origins="https://app.example.com",
    )

    assert settings.environment is Environment.PRODUCTION
    assert settings.is_production is True
