from __future__ import annotations

from enum import Enum as PyEnum

from sqlalchemy import Enum as SQLEnum


class UserRole(str, PyEnum):
    CUSTOMER = "customer"
    TECHNICIAN = "technician"
    ADMIN = "admin"


class Priority(str, PyEnum):
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class ComplaintChannel(str, PyEnum):
    WEB = "web"
    WHATSAPP = "whatsapp"


class ComplaintStatus(str, PyEnum):
    RECEIVED = "received"
    ANALYZING = "analyzing"
    AWAITING_CUSTOMER = "awaiting_customer"
    READY_FOR_WORK_ORDER = "ready_for_work_order"
    CONVERTED = "converted"
    ESCALATED = "escalated"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class WorkOrderStatus(str, PyEnum):
    DRAFT = "draft"
    VALIDATED = "validated"
    AWAITING_ASSIGNMENT = "awaiting_assignment"
    ASSIGNED = "assigned"
    ACCEPTED = "accepted"
    IN_PROGRESS = "in_progress"
    AWAITING_PARTS = "awaiting_parts"
    PENDING_VERIFICATION = "pending_verification"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ESCALATED = "escalated"


class AssignmentStatus(str, PyEnum):
    OFFERED = "offered"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    EXPIRED = "expired"


class MessageSenderType(str, PyEnum):
    CUSTOMER = "customer"
    ASSISTANT = "assistant"
    STAFF = "staff"


class MediaType(str, PyEnum):
    IMAGE = "image"
    AUDIO = "audio"
    DOCUMENT = "document"


class EvidenceStatus(str, PyEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"


class WorkflowRunStatus(str, PyEnum):
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class IngestionStatus(str, PyEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


def enum_type(
    enum_cls: type[PyEnum],
    name: str,
    length: int = 40,
) -> SQLEnum:
    return SQLEnum(
        enum_cls,
        name=name,
        length=length,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda enum: [member.value for member in enum],
    )


__all__ = [
    "AssignmentStatus",
    "ComplaintChannel",
    "ComplaintStatus",
    "EvidenceStatus",
    "IngestionStatus",
    "MediaType",
    "MessageSenderType",
    "Priority",
    "UserRole",
    "WorkOrderStatus",
    "WorkflowRunStatus",
    "enum_type",
]
