from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import (
    DEFAULT_CELERY_OUTBOX_DISPATCH_LIMIT,
    DEFAULT_CELERY_OUTBOX_MAX_PUBLISH_ATTEMPTS,
    DEFAULT_CELERY_TASK_MAX_RETRIES,
    DEFAULT_CELERY_TASK_RETRY_BACKOFF_MAX_SECONDS,
    DEFAULT_CELERY_TASK_RETRY_BACKOFF_SECONDS,
    DEFAULT_CELERY_TASK_SOFT_TIME_LIMIT_SECONDS,
    DEFAULT_CELERY_TASK_TIME_LIMIT_SECONDS,
    DEFAULT_DATABASE_URL,
    DEFAULT_REDIS_URL,
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
    "CLERK_SECRET_KEY",
    "CLERK_JWT_KEY",
    "CLERK_AUTHORIZED_PARTIES",
    "AUTH_BOOTSTRAP_RATE_LIMIT_PER_IP",
    "AUTH_BOOTSTRAP_RATE_LIMIT_PER_SUBJECT",
    "AUTH_BOOTSTRAP_RATE_LIMIT_WINDOW_SECONDS",
    "GOOGLE_API_KEY",
    "EMBEDDING_MODEL",
    "EMBEDDING_DIMENSIONS",
    "RETRIEVAL_DEFAULT_TOP_K",
    "RETRIEVAL_MAX_TOP_K",
    "OPENAI_API_KEY",
    "CHAT_MODEL",
    "CHAT_TEMPERATURE",
    "CHAT_TIMEOUT_SECONDS",
    "CHAT_MAX_RETRIES",
    "CHAT_MAX_OUTPUT_TOKENS",
    "ANSWER_MIN_SIMILARITY",
    "ANSWER_MAX_CONTEXT_CHARS",
    "REDIS_URL",
    "CELERY_BROKER_URL",
    "CELERY_RESULT_BACKEND",
    "CELERY_TASK_ALWAYS_EAGER",
    "CELERY_TASK_EAGER_PROPAGATES",
    "CELERY_TASK_MAX_RETRIES",
    "CELERY_TASK_RETRY_BACKOFF_SECONDS",
    "CELERY_TASK_RETRY_BACKOFF_MAX_SECONDS",
    "CELERY_TASK_TIME_LIMIT_SECONDS",
    "CELERY_TASK_SOFT_TIME_LIMIT_SECONDS",
    "CELERY_OUTBOX_DISPATCH_LIMIT",
    "CELERY_OUTBOX_MAX_PUBLISH_ATTEMPTS",
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
        "clerk_secret_key": "sk_test_production_placeholder",
        "clerk_authorized_parties": "https://app.example.com",
        "google_api_key": "test-google-api-key",
        "openai_api_key": "test-openai-api-key",
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
    assert settings.auth_bootstrap_rate_limit_per_ip == 30
    assert settings.auth_bootstrap_rate_limit_per_subject == 10
    assert settings.auth_bootstrap_rate_limit_window_seconds == 60
    assert settings.google_api_key is None
    assert settings.embedding_model == "gemini-embedding-001"
    assert settings.embedding_dimensions == 1536
    assert settings.retrieval_default_top_k == 5
    assert settings.retrieval_max_top_k == 20
    assert settings.openai_api_key is None
    assert settings.chat_model == "gpt-4o-mini"
    assert settings.chat_temperature == 0.0
    assert settings.chat_timeout_seconds == 30.0
    assert settings.chat_max_retries == 0
    assert settings.chat_max_output_tokens == 1024
    assert settings.answer_min_similarity == 0.3
    assert settings.answer_max_context_chars == 16000
    assert settings.redis_url == DEFAULT_REDIS_URL
    assert settings.celery_broker_url is None
    assert settings.celery_result_backend is None
    assert settings.effective_celery_broker_url == DEFAULT_REDIS_URL
    assert settings.effective_celery_result_backend == DEFAULT_REDIS_URL
    assert settings.celery_task_always_eager is False
    assert settings.celery_task_eager_propagates is True
    assert settings.celery_task_max_retries == DEFAULT_CELERY_TASK_MAX_RETRIES
    assert (
        settings.celery_task_retry_backoff_seconds
        == DEFAULT_CELERY_TASK_RETRY_BACKOFF_SECONDS
    )
    assert (
        settings.celery_task_retry_backoff_max_seconds
        == DEFAULT_CELERY_TASK_RETRY_BACKOFF_MAX_SECONDS
    )
    assert (
        settings.celery_task_time_limit_seconds
        == DEFAULT_CELERY_TASK_TIME_LIMIT_SECONDS
    )
    assert (
        settings.celery_task_soft_time_limit_seconds
        == DEFAULT_CELERY_TASK_SOFT_TIME_LIMIT_SECONDS
    )
    assert (
        settings.celery_outbox_dispatch_limit
        == DEFAULT_CELERY_OUTBOX_DISPATCH_LIMIT
    )
    assert (
        settings.celery_outbox_max_publish_attempts
        == DEFAULT_CELERY_OUTBOX_MAX_PUBLISH_ATTEMPTS
    )


@pytest.mark.parametrize(
    "field",
    [
        "auth_bootstrap_rate_limit_per_ip",
        "auth_bootstrap_rate_limit_per_subject",
        "auth_bootstrap_rate_limit_window_seconds",
    ],
)
def test_rate_limit_settings_must_be_positive(field: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: 0})


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
        production_settings(debug=True)


def test_production_rejects_default_database_url() -> None:
    with pytest.raises(ValidationError):
        production_settings(database_url=DEFAULT_DATABASE_URL)


def test_production_rejects_placeholder_credentials() -> None:
    with pytest.raises(ValidationError):
        production_settings(
            database_url=(
                "postgresql+asyncpg://fieldops:fieldops@db.example.com/prod"
            )
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


def test_clerk_authorized_parties_are_parsed() -> None:
    settings = Settings(
        _env_file=None,
        clerk_authorized_parties=(
            "https://app.example.com, https://admin.example.com ,"
        ),
    )

    assert settings.clerk_authorized_parties_list == [
        "https://app.example.com",
        "https://admin.example.com",
    ]


def test_clerk_jwt_key_literal_newlines_are_normalized() -> None:
    settings = Settings(
        _env_file=None,
        clerk_jwt_key="-----BEGIN PUBLIC KEY-----\\nMIIB\\n-----END PUBLIC KEY-----",
    )

    assert settings.clerk_jwt_key == (
        "-----BEGIN PUBLIC KEY-----\nMIIB\n-----END PUBLIC KEY-----"
    )


def test_production_requires_clerk_configuration() -> None:
    with pytest.raises(ValidationError):
        production_settings(
            clerk_secret_key=None,
            clerk_jwt_key=None,
        )


def test_production_rejects_wildcard_clerk_authorized_parties() -> None:
    with pytest.raises(ValidationError):
        production_settings(clerk_authorized_parties="*")


def test_production_rejects_empty_clerk_authorized_parties() -> None:
    with pytest.raises(ValidationError):
        production_settings(clerk_authorized_parties=" , ")


def test_google_api_key_is_trimmed_and_blank_is_none() -> None:
    settings = Settings(_env_file=None, google_api_key="  test-key  ")

    assert settings.google_api_key == "test-key"
    assert Settings(_env_file=None, google_api_key="   ").google_api_key is None


def test_embedding_dimensions_are_fixed_for_current_schema() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, embedding_dimensions=768)


def test_retrieval_top_k_settings_are_bounded() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, retrieval_default_top_k=0)
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            retrieval_default_top_k=10,
            retrieval_max_top_k=5,
        )


def test_production_requires_google_api_key() -> None:
    with pytest.raises(ValidationError):
        production_settings(google_api_key=None)


def test_openai_api_key_is_trimmed_and_blank_is_none() -> None:
    settings = Settings(_env_file=None, openai_api_key="  test-key  ")

    assert settings.openai_api_key == "test-key"
    assert Settings(_env_file=None, openai_api_key="   ").openai_api_key is None


def test_chat_model_must_not_be_blank() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, chat_model="   ")


def test_chat_generation_settings_are_bounded() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, chat_temperature=2.5)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, chat_timeout_seconds=0)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, chat_max_retries=-1)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, answer_min_similarity=1.5)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, answer_max_context_chars=0)


def test_production_requires_openai_api_key() -> None:
    with pytest.raises(ValidationError):
        production_settings(openai_api_key=None)


def test_redis_urls_accept_redis_and_rediss_schemes() -> None:
    settings = Settings(
        _env_file=None,
        redis_url="rediss://redis.example.com:6380/1",
        celery_broker_url="redis://broker.example.com:6379/2",
        celery_result_backend="redis://backend.example.com:6379/3",
    )

    assert settings.redis_url == "rediss://redis.example.com:6380/1"
    assert (
        settings.effective_celery_broker_url
        == "redis://broker.example.com:6379/2"
    )
    assert (
        settings.effective_celery_result_backend
        == "redis://backend.example.com:6379/3"
    )


def test_redis_urls_reject_non_redis_schemes() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, redis_url="http://localhost:6379/0")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, redis_url="redis://")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, celery_broker_url="amqp://localhost")


def test_celery_settings_are_bounded_and_ordered() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, celery_task_max_retries=-1)
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            celery_task_soft_time_limit_seconds=900,
            celery_task_time_limit_seconds=900,
        )
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            celery_task_retry_backoff_seconds=120,
            celery_task_retry_backoff_max_seconds=60,
        )
