from __future__ import annotations

from enum import Enum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

BACKEND_DIR = Path(__file__).resolve().parents[2]

DEFAULT_DATABASE_URL = "postgresql+asyncpg://fieldops:fieldops@localhost:5432/fieldops"
DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"
DEFAULT_STORAGE_ROOT = BACKEND_DIR / "var" / "document_storage"
DEFAULT_MAX_UPLOAD_SIZE_BYTES = 25 * 1024 * 1024
DEFAULT_MAX_PDF_PAGES = 500
DEFAULT_DOCUMENT_CHUNK_SIZE = 1000
DEFAULT_DOCUMENT_CHUNK_OVERLAP = 200
DEFAULT_DOCUMENT_INGESTION_VERSION = "1"
DEFAULT_REQUEST_BODY_OVERHEAD_BYTES = 64 * 1024
DEFAULT_INGESTION_STALE_AFTER_SECONDS = 30 * 60
DEFAULT_EMBEDDING_MODEL = "gemini-embedding-001"
DEFAULT_EMBEDDING_DIMENSIONS = 1536
DEFAULT_RETRIEVAL_TOP_K = 5
DEFAULT_RETRIEVAL_MAX_TOP_K = 20
DEFAULT_CHAT_MODEL = "gpt-4o-mini"
DEFAULT_CHAT_TEMPERATURE = 0.0
DEFAULT_CHAT_TIMEOUT_SECONDS = 30.0
DEFAULT_CHAT_MAX_RETRIES = 0
DEFAULT_CHAT_MAX_OUTPUT_TOKENS = 1024
DEFAULT_ANSWER_MIN_SIMILARITY = 0.3
DEFAULT_ANSWER_MAX_CONTEXT_CHARS = 16000
SUPPORTED_STORAGE_BACKENDS = frozenset({"local"})

VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
SAFE_TLS_MODES = frozenset({"require", "verify-ca", "verify-full"})
WEAK_DATABASE_PASSWORDS = frozenset(
    {
        "fieldops",
        "changeme",
        "password",
        "postgres",
        "admin",
        "root",
        "test",
        "secret",
        "123456",
        "letmein",
        "qwerty",
    }
)
WEAK_DATABASE_CREDENTIAL_PAIRS = frozenset(
    {
        "fieldops:fieldops",
        "postgres:postgres",
        "admin:admin",
        "root:root",
        "test:test",
        "user:password",
        "user:pass",
    }
)


class Environment(str, Enum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "FieldOps AI"
    app_version: str = "0.1.0"
    environment: Environment = Environment.DEVELOPMENT
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    database_url: str = DEFAULT_DATABASE_URL
    cors_origins: str = DEFAULT_CORS_ORIGINS
    cors_allow_credentials: bool = True
    log_level: str = "INFO"

    clerk_secret_key: str | None = None
    clerk_jwt_key: str | None = None
    clerk_authorized_parties: str = DEFAULT_CORS_ORIGINS

    storage_backend: str = "local"
    storage_root: Path = DEFAULT_STORAGE_ROOT
    max_upload_size_bytes: int = Field(
        default=DEFAULT_MAX_UPLOAD_SIZE_BYTES,
        ge=1,
    )
    request_body_overhead_bytes: int = Field(
        default=DEFAULT_REQUEST_BODY_OVERHEAD_BYTES,
        ge=0,
    )
    ingestion_stale_after_seconds: int = Field(
        default=DEFAULT_INGESTION_STALE_AFTER_SECONDS,
        ge=1,
    )
    allowed_document_content_types: str = "application/pdf"
    max_pdf_pages: int = Field(default=DEFAULT_MAX_PDF_PAGES, ge=1)
    document_chunk_size: int = Field(
        default=DEFAULT_DOCUMENT_CHUNK_SIZE,
        ge=1,
    )
    document_chunk_overlap: int = Field(
        default=DEFAULT_DOCUMENT_CHUNK_OVERLAP,
        ge=0,
    )
    document_ingestion_version: str = DEFAULT_DOCUMENT_INGESTION_VERSION

    google_api_key: str | None = None
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    embedding_dimensions: int = Field(
        default=DEFAULT_EMBEDDING_DIMENSIONS,
        ge=1,
    )
    retrieval_default_top_k: int = Field(
        default=DEFAULT_RETRIEVAL_TOP_K,
        ge=1,
        le=DEFAULT_RETRIEVAL_MAX_TOP_K,
    )
    retrieval_max_top_k: int = Field(
        default=DEFAULT_RETRIEVAL_MAX_TOP_K,
        ge=1,
        le=100,
    )

    openai_api_key: str | None = None
    chat_model: str = DEFAULT_CHAT_MODEL
    chat_temperature: float = Field(
        default=DEFAULT_CHAT_TEMPERATURE,
        ge=0.0,
        le=2.0,
    )
    chat_timeout_seconds: float = Field(
        default=DEFAULT_CHAT_TIMEOUT_SECONDS,
        gt=0,
    )
    chat_max_retries: int = Field(default=DEFAULT_CHAT_MAX_RETRIES, ge=0)
    chat_max_output_tokens: int = Field(
        default=DEFAULT_CHAT_MAX_OUTPUT_TOKENS,
        ge=1,
    )
    answer_min_similarity: float = Field(
        default=DEFAULT_ANSWER_MIN_SIMILARITY,
        ge=0.0,
        le=1.0,
    )
    answer_max_context_chars: int = Field(
        default=DEFAULT_ANSWER_MAX_CONTEXT_CHARS,
        ge=1,
    )

    auth_bootstrap_rate_limit_per_ip: int = Field(default=30, ge=1)
    auth_bootstrap_rate_limit_per_subject: int = Field(default=10, ge=1)
    auth_bootstrap_rate_limit_window_seconds: int = Field(
        default=60,
        ge=1,
    )

    db_pool_size: int = Field(default=5, ge=1)
    db_max_overflow: int = Field(default=10, ge=0)
    db_pool_timeout: float = Field(default=30.0, gt=0)
    db_connect_timeout: float = Field(default=5.0, gt=0)
    db_echo: bool = False
    db_require_tls: bool = True

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+asyncpg://", 1)
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+asyncpg://", 1)
        return value

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        try:
            url = make_url(value)
        except (ArgumentError, ValueError) as exc:
            raise ValueError("DATABASE_URL must be a valid PostgreSQL URL") from exc

        if url.drivername != "postgresql+asyncpg":
            raise ValueError(
                "DATABASE_URL must use the asyncpg driver (postgresql+asyncpg://...)"
            )

        if not url.host:
            raise ValueError("DATABASE_URL must include a hostname")

        if not url.database:
            raise ValueError("DATABASE_URL must include a database name")

        if url.port is not None:
            try:
                port = int(url.port)
            except (TypeError, ValueError) as exc:
                raise ValueError("DATABASE_URL must include a valid port") from exc
            if not 1 <= port <= 65535:
                raise ValueError("DATABASE_URL port must be between 1 and 65535")

        return value

    @field_validator("api_v1_prefix")
    @classmethod
    def validate_api_v1_prefix(cls, value: str) -> str:
        prefix = value.strip()
        if not prefix.startswith("/"):
            prefix = f"/{prefix}"
        return prefix.rstrip("/") or "/"

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        level = value.strip().upper()
        if level not in VALID_LOG_LEVELS:
            raise ValueError(f"LOG_LEVEL must be one of {sorted(VALID_LOG_LEVELS)}")
        return level

    @field_validator("clerk_secret_key", "clerk_jwt_key", mode="before")
    @classmethod
    def normalize_optional_secret(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("clerk_authorized_parties")
    @classmethod
    def validate_clerk_authorized_parties(cls, value: str) -> str:
        parties = [party.strip() for party in value.split(",") if party.strip()]
        if not parties:
            raise ValueError(
                "CLERK_AUTHORIZED_PARTIES must contain at least one origin"
            )
        if "*" in parties:
            raise ValueError("CLERK_AUTHORIZED_PARTIES must not use a wildcard origin")
        return ",".join(parties)

    @field_validator("clerk_jwt_key")
    @classmethod
    def normalize_clerk_jwt_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.replace("\\n", "\n")

    @field_validator("storage_backend")
    @classmethod
    def validate_storage_backend(cls, value: str) -> str:
        backend = value.strip().lower()
        if backend not in SUPPORTED_STORAGE_BACKENDS:
            raise ValueError(
                f"STORAGE_BACKEND must be one of {sorted(SUPPORTED_STORAGE_BACKENDS)}"
            )
        return backend

    @field_validator("storage_root", mode="before")
    @classmethod
    def normalize_storage_root(cls, value: object) -> Path:
        path = Path(str(value)).expanduser()
        if not path.is_absolute():
            path = BACKEND_DIR / path
        return path.resolve()

    @field_validator("allowed_document_content_types")
    @classmethod
    def validate_allowed_document_content_types(cls, value: str) -> str:
        content_types = [
            item.strip().lower() for item in value.split(",") if item.strip()
        ]
        if not content_types:
            raise ValueError(
                "ALLOWED_DOCUMENT_CONTENT_TYPES must contain at least one content type"
            )
        return ",".join(content_types)

    @field_validator("document_ingestion_version")
    @classmethod
    def validate_document_ingestion_version(cls, value: str) -> str:
        version = value.strip()
        if not version:
            raise ValueError("DOCUMENT_INGESTION_VERSION must not be blank")
        return version

    @field_validator("google_api_key", mode="before")
    @classmethod
    def normalize_google_api_key(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("embedding_model")
    @classmethod
    def validate_embedding_model(cls, value: str) -> str:
        model = value.strip()
        if not model:
            raise ValueError("EMBEDDING_MODEL must not be blank")
        return model

    @field_validator("openai_api_key", mode="before")
    @classmethod
    def normalize_openai_api_key(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("chat_model")
    @classmethod
    def validate_chat_model(cls, value: str) -> str:
        model = value.strip()
        if not model:
            raise ValueError("CHAT_MODEL must not be blank")
        return model

    @model_validator(mode="after")
    def validate_embedding_settings(self) -> Settings:
        if self.embedding_dimensions != DEFAULT_EMBEDDING_DIMENSIONS:
            raise ValueError(
                "EMBEDDING_DIMENSIONS is fixed at "
                f"{DEFAULT_EMBEDDING_DIMENSIONS} for the current pgvector "
                "schema. Change the embedding model and vector-column "
                "migration together before changing it."
            )
        if self.retrieval_default_top_k > self.retrieval_max_top_k:
            raise ValueError(
                "RETRIEVAL_DEFAULT_TOP_K must not exceed RETRIEVAL_MAX_TOP_K"
            )
        return self

    @model_validator(mode="after")
    def validate_ingestion_settings(self) -> Settings:
        if self.document_chunk_overlap >= self.document_chunk_size:
            raise ValueError(
                "DOCUMENT_CHUNK_OVERLAP must be smaller than DOCUMENT_CHUNK_SIZE"
            )
        return self

    @model_validator(mode="after")
    def validate_production_settings(self) -> Settings:
        if self.environment is not Environment.PRODUCTION:
            return self

        if self.debug:
            raise ValueError("DEBUG must be disabled in production")

        if self.database_url == DEFAULT_DATABASE_URL:
            raise ValueError("DATABASE_URL must be configured for production")

        url = make_url(self.database_url)
        username = (url.username or "").strip()
        password = (url.password or "").strip()
        if not username or not password:
            raise ValueError(
                "DATABASE_URL must include a non-empty username and password "
                "in production"
            )

        credential_pair = f"{username}:{password}".lower()
        if (
            credential_pair in WEAK_DATABASE_CREDENTIAL_PAIRS
            or password.lower() in WEAK_DATABASE_PASSWORDS
        ):
            raise ValueError(
                "DATABASE_URL must not use weak placeholder credentials in production"
            )

        if not self.allowed_origins:
            raise ValueError("CORS_ORIGINS must be configured in production")

        if self.cors_allow_credentials and "*" in self.allowed_origins:
            raise ValueError(
                "CORS_ORIGINS must not use a wildcard origin while "
                "credentials are enabled in production"
            )

        if not self.clerk_secret_key and not self.clerk_jwt_key:
            raise ValueError(
                "CLERK_SECRET_KEY or CLERK_JWT_KEY must be configured in production"
            )

        if not self.clerk_authorized_parties_list:
            raise ValueError(
                "CLERK_AUTHORIZED_PARTIES must be configured in production"
            )

        if not self.google_api_key:
            raise ValueError(
                "GOOGLE_API_KEY must be configured in production for "
                "document embeddings"
            )

        if not self.openai_api_key:
            raise ValueError(
                "OPENAI_API_KEY must be configured in production for "
                "grounded answer generation"
            )

        if self.db_echo:
            raise ValueError("DB_ECHO must be disabled in production")

        if self.db_require_tls:
            ssl_mode = str(url.query.get("ssl", "")).strip().lower()
            if ssl_mode not in SAFE_TLS_MODES:
                raise ValueError(
                    "DATABASE_URL must enable TLS in production "
                    "(ssl=require, ssl=verify-ca or ssl=verify-full); "
                    "set DB_REQUIRE_TLS=false only when TLS is terminated "
                    "elsewhere"
                )

        return self

    @property
    def max_request_body_bytes(self) -> int:
        """Upper bound for any request body before multipart parsing.

        Uploaded files are limited to ``max_upload_size_bytes``; the multipart
        envelope needs a bounded allowance for headers, boundaries and form
        fields. Applying the bound to every request is intentional so no
        alternate request path can bypass it.
        """

        return self.max_upload_size_bytes + self.request_body_overhead_bytes

    @property
    def allowed_origins(self) -> list[str]:
        return [
            origin.strip() for origin in self.cors_origins.split(",") if origin.strip()
        ]

    @property
    def allowed_document_content_types_list(self) -> list[str]:
        return [
            item.strip().lower()
            for item in self.allowed_document_content_types.split(",")
            if item.strip()
        ]

    @property
    def clerk_authorized_parties_list(self) -> list[str]:
        return [
            party.strip()
            for party in self.clerk_authorized_parties.split(",")
            if party.strip()
        ]

    @property
    def is_production(self) -> bool:
        return self.environment is Environment.PRODUCTION


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
