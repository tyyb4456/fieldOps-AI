from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class CustomerProfileResponse(BaseModel):
    id: uuid.UUID
    full_name: str
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    preferred_language: str | None = None
    is_active: bool
    created_at: datetime


class CustomerUpdate(BaseModel):
    """Fields a customer may change on their own profile.

    Account identity, role, activation and administrative fields are
    intentionally absent. ``extra="forbid"`` turns attempts to send them into
    a validation error instead of silently ignoring them.
    """

    model_config = ConfigDict(extra="forbid")

    address: str | None = Field(default=None, max_length=2000)
    preferred_language: str | None = Field(
        default=None,
        min_length=2,
        max_length=30,
    )

    @field_validator("address")
    @classmethod
    def normalize_address(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("preferred_language")
    @classmethod
    def normalize_language(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("preferred_language must not be blank")
        return stripped

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> CustomerUpdate:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        return self
