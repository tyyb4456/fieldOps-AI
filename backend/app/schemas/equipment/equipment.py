from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class EquipmentResponse(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    manufacturer: str
    model: str
    serial_number: str | None = None
    equipment_type: str
    installation_date: date | None = None
    created_at: datetime


class EquipmentListResponse(BaseModel):
    items: list[EquipmentResponse]
    total: int
    limit: int
    offset: int


def _normalize_serial_number(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _validate_installation_date(value: date | None) -> date | None:
    if value is not None and value > date.today():
        raise ValueError("installation_date must not be in the future")
    return value


class EquipmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manufacturer: str = Field(min_length=1, max_length=150)
    model: str = Field(min_length=1, max_length=150)
    serial_number: str | None = Field(default=None, max_length=150)
    equipment_type: str = Field(min_length=1, max_length=80)
    installation_date: date | None = None

    @field_validator("manufacturer", "model", "equipment_type")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Field must not be blank")
        return stripped

    @field_validator("serial_number")
    @classmethod
    def normalize_serial_number(cls, value: str | None) -> str | None:
        return _normalize_serial_number(value)

    @field_validator("installation_date")
    @classmethod
    def validate_installation_date(cls, value: date | None) -> date | None:
        return _validate_installation_date(value)


class EquipmentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manufacturer: str | None = Field(
        default=None,
        min_length=1,
        max_length=150,
    )
    model: str | None = Field(default=None, min_length=1, max_length=150)
    serial_number: str | None = Field(default=None, max_length=150)
    equipment_type: str | None = Field(
        default=None,
        min_length=1,
        max_length=80,
    )
    installation_date: date | None = None

    @field_validator("manufacturer", "model", "equipment_type")
    @classmethod
    def normalize_required_text(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("Field may not be null")
        stripped = value.strip()
        if not stripped:
            raise ValueError("Field must not be blank")
        return stripped

    @field_validator("serial_number")
    @classmethod
    def normalize_serial_number(cls, value: str | None) -> str | None:
        return _normalize_serial_number(value)

    @field_validator("installation_date")
    @classmethod
    def validate_installation_date(cls, value: date | None) -> date | None:
        return _validate_installation_date(value)

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> EquipmentUpdate:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        return self
