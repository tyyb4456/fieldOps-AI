from __future__ import annotations

import uuid

from pydantic import BaseModel

from app.models.enums import UserRole


class UserMeResponse(BaseModel):
    id: uuid.UUID
    full_name: str
    email: str | None = None
    phone: str | None = None
    role: UserRole
    is_active: bool
    customer_id: uuid.UUID | None = None
    technician_id: uuid.UUID | None = None
