"""Administrator-driven lifecycle transitions with readiness enforcement."""

from __future__ import annotations

import uuid
from collections.abc import Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ComplaintStatus
from app.services.complaints import lifecycle_service
from app.services.complaints.lifecycle import (
    LifecycleActor,
    ReadinessMarker,
    coerce_status,
    validate_transition,
    validate_transition_fields,
)
from app.services.complaints.readiness import confirm_readiness


async def transition_complaint_as_admin(
    session: AsyncSession,
    *,
    complaint_id: uuid.UUID,
    target_status: ComplaintStatus | str,
    expected_status: ComplaintStatus | str,
    fields: Mapping[str, object] | None = None,
    actor_id: uuid.UUID | None = None,
    diagnostic_workflow_run_id: uuid.UUID | None = None,
) -> lifecycle_service.LifecycleTransition:
    """Apply one admin transition after the readiness gate, under one lock."""

    complaint = await lifecycle_service.lock_complaint(session, complaint_id)
    target = coerce_status(target_status)
    request_fields = dict(fields or {})

    validate_transition(
        complaint.status,
        target,
        LifecycleActor.ADMIN,
        expected_status=expected_status,
    )
    validate_transition_fields(target, request_fields)

    readiness_marker: ReadinessMarker | None = None
    if target is ComplaintStatus.READY_FOR_WORK_ORDER:
        readiness_marker = await confirm_readiness(
            session,
            complaint,
            requested_run_id=diagnostic_workflow_run_id,
        )

    return await lifecycle_service.transition_locked_complaint(
        session,
        complaint=complaint,
        target_status=target,
        actor=LifecycleActor.ADMIN,
        actor_id=actor_id,
        expected_status=expected_status,
        fields=request_fields,
        readiness_marker=readiness_marker,
    )


__all__ = ["transition_complaint_as_admin"]
