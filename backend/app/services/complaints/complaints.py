from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.complaint import Complaint
from app.models.complaint_history import ComplaintHistory
from app.models.customer import Customer
from app.models.enums import ComplaintStatus, Priority
from app.schemas.complaints.complaint import ComplaintCreate, ComplaintUpdate
from app.services.equipment.equipment import get_equipment_for_customer
from app.services.shared.authorization import AccessDeniedError

CUSTOMER_EDITABLE_STATUSES = frozenset(
    {
        ComplaintStatus.RECEIVED,
        ComplaintStatus.AWAITING_CUSTOMER,
    }
)

# A customer may end the complaint process only while no operational work is
# underway. Once a work order exists (converted) or the case has been escalated
# or closed, cancellation is an internal operation, not a customer action.
CUSTOMER_ALLOWED_TRANSITIONS: dict[
    ComplaintStatus, frozenset[ComplaintStatus]
] = {
    ComplaintStatus.RECEIVED: frozenset({ComplaintStatus.CANCELLED}),
    ComplaintStatus.ANALYZING: frozenset({ComplaintStatus.CANCELLED}),
    ComplaintStatus.AWAITING_CUSTOMER: frozenset(
        {ComplaintStatus.CANCELLED}
    ),
    ComplaintStatus.READY_FOR_WORK_ORDER: frozenset(
        {ComplaintStatus.CANCELLED}
    ),
}


class InvalidComplaintTransitionError(Exception):
    """Raised when a customer requests a disallowed complaint state change."""


def validate_customer_transition(
    current: ComplaintStatus,
    target: ComplaintStatus,
) -> None:
    allowed = CUSTOMER_ALLOWED_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise InvalidComplaintTransitionError(
            f"Customer cannot move complaint from {current.value} "
            f"to {target.value}"
        )


async def list_complaints(
    session: AsyncSession,
    *,
    customer_id: uuid.UUID | None,
    status: ComplaintStatus | None,
    equipment_id: uuid.UUID | None,
    created_from: datetime | None,
    created_to: datetime | None,
    limit: int,
    offset: int,
) -> tuple[list[Complaint], int]:
    filters = []
    if customer_id is not None:
        filters.append(Complaint.customer_id == customer_id)
    if status is not None:
        filters.append(Complaint.status == status)
    if equipment_id is not None:
        filters.append(Complaint.equipment_id == equipment_id)
    if created_from is not None:
        filters.append(Complaint.created_at >= created_from)
    if created_to is not None:
        filters.append(Complaint.created_at <= created_to)

    total = await session.scalar(
        select(func.count()).select_from(Complaint).where(*filters)
    )

    statement = (
        select(Complaint)
        .where(*filters)
        .order_by(Complaint.created_at.desc(), Complaint.id.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(statement)
    return list(result.scalars().all()), int(total or 0)


async def get_complaint(
    session: AsyncSession,
    complaint_id: uuid.UUID,
    *,
    customer_id: uuid.UUID | None = None,
    for_update: bool = False,
) -> Complaint:
    statement = select(Complaint).where(Complaint.id == complaint_id)
    if customer_id is not None:
        statement = statement.where(Complaint.customer_id == customer_id)
    if for_update:
        statement = statement.with_for_update()

    result = await session.execute(statement)
    complaint = result.scalar_one_or_none()
    if complaint is None:
        raise AccessDeniedError("Complaint not found")
    return complaint


async def list_complaint_history(
    session: AsyncSession,
    complaint_id: uuid.UUID,
) -> list[ComplaintHistory]:
    result = await session.execute(
        select(ComplaintHistory)
        .where(ComplaintHistory.complaint_id == complaint_id)
        .order_by(ComplaintHistory.sequence_number.asc())
    )
    return list(result.scalars().all())


async def _lock_complaint_row(
    session: AsyncSession,
    complaint_id: uuid.UUID,
) -> None:
    """Serialize all history writers for one complaint.

    The row lock is held until the surrounding transaction commits. Every
    history-writing path must acquire it before allocating a sequence so two
    concurrent transactions can never observe the same maximum sequence.
    """
    await session.execute(
        select(Complaint.id)
        .where(Complaint.id == complaint_id)
        .with_for_update()
    )


async def _append_history(
    session: AsyncSession,
    *,
    complaint_id: uuid.UUID,
    event_type: str,
    from_status: ComplaintStatus | None,
    to_status: ComplaintStatus | None,
    changed_fields: dict[str, Any],
    actor_id: uuid.UUID | None,
) -> ComplaintHistory:
    await _lock_complaint_row(session, complaint_id)
    last_sequence = await session.scalar(
        select(func.max(ComplaintHistory.sequence_number)).where(
            ComplaintHistory.complaint_id == complaint_id
        )
    )
    entry = ComplaintHistory(
        complaint_id=complaint_id,
        sequence_number=int(last_sequence or 0) + 1,
        event_type=event_type,
        from_status=from_status,
        to_status=to_status,
        changed_fields=changed_fields,
        actor_id=actor_id,
    )
    session.add(entry)
    await session.flush()
    return entry


async def append_complaint_history(
    session: AsyncSession,
    *,
    complaint_id: uuid.UUID,
    event_type: str,
    from_status: ComplaintStatus | None,
    to_status: ComplaintStatus | None,
    changed_fields: dict[str, Any],
    actor_id: uuid.UUID | None,
) -> ComplaintHistory:
    """Append one history event while holding the complaint row lock.

    Exposed for other business operations (for example complaint conversion)
    that must record an audit event in the same transaction as their own
    mutation.
    """
    return await _append_history(
        session,
        complaint_id=complaint_id,
        event_type=event_type,
        from_status=from_status,
        to_status=to_status,
        changed_fields=changed_fields,
        actor_id=actor_id,
    )


async def create_complaint(
    session: AsyncSession,
    *,
    customer: Customer,
    data: ComplaintCreate,
    actor_id: uuid.UUID | None = None,
) -> Complaint:
    if data.equipment_id is not None:
        await get_equipment_for_customer(
            session,
            customer.id,
            data.equipment_id,
        )

    complaint = Complaint(
        customer_id=customer.id,
        equipment_id=data.equipment_id,
        description=data.description,
        reported_error_code=data.reported_error_code,
        channel=data.channel,
        status=ComplaintStatus.RECEIVED,
        priority=Priority.NORMAL,
    )
    session.add(complaint)
    await session.flush()
    await _append_history(
        session,
        complaint_id=complaint.id,
        event_type="created",
        from_status=None,
        to_status=ComplaintStatus.RECEIVED,
        changed_fields={},
        actor_id=actor_id,
    )
    return complaint


async def update_complaint(
    session: AsyncSession,
    complaint: Complaint,
    data: ComplaintUpdate,
    *,
    actor_id: uuid.UUID | None = None,
) -> Complaint:
    # Service-level lock so internal callers get the same serialization
    # guarantee as the HTTP routes, which already load with FOR UPDATE.
    await session.refresh(complaint, with_for_update=True)
    if complaint.status not in CUSTOMER_EDITABLE_STATUSES:
        raise InvalidComplaintTransitionError(
            "Complaint is not editable in its current state"
        )

    changes: dict[str, dict[str, object]] = {}
    for field in data.model_fields_set:
        old_value = getattr(complaint, field)
        new_value = getattr(data, field)
        if old_value != new_value:
            changes[field] = {"from": old_value, "to": new_value}
            setattr(complaint, field, new_value)

    if changes:
        await _append_history(
            session,
            complaint_id=complaint.id,
            event_type="updated",
            from_status=complaint.status,
            to_status=complaint.status,
            changed_fields=changes,
            actor_id=actor_id,
        )

    await session.flush()
    return complaint


async def cancel_complaint(
    session: AsyncSession,
    complaint: Complaint,
    *,
    actor_id: uuid.UUID | None = None,
) -> Complaint:
    # Service-level lock so internal callers get the same serialization
    # guarantee as the HTTP routes, which already load with FOR UPDATE.
    await session.refresh(complaint, with_for_update=True)
    previous_status = complaint.status
    validate_customer_transition(
        previous_status,
        ComplaintStatus.CANCELLED,
    )
    complaint.status = ComplaintStatus.CANCELLED
    await _append_history(
        session,
        complaint_id=complaint.id,
        event_type="cancelled",
        from_status=previous_status,
        to_status=ComplaintStatus.CANCELLED,
        changed_fields={
            "status": {
                "from": previous_status.value,
                "to": ComplaintStatus.CANCELLED.value,
            }
        },
        actor_id=actor_id,
    )
    await session.flush()
    return complaint
