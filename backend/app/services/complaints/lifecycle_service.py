"""Transactional complaint lifecycle service.

This module is the single writer for complaint lifecycle status changes and for
system invalidation of pending work-order proposals. It connects the pure
policy in :mod:`app.services.complaints.lifecycle` to PostgreSQL, but keeps the
policy itself free of database or configuration access.

Lock order (authoritative for every caller):

1. ``complaints`` row (``FOR UPDATE``).
2. readiness diagnostic ``workflow_runs`` row (``FOR SHARE``; conversion and
   approval only, implemented by the readiness validator in a later step).
3. ``work_order_proposals`` row (``FOR UPDATE``).

A transaction must never acquire a lower-numbered lock after a higher-numbered
one. Proposal rejection may lock only the proposal and must not touch the
complaint afterwards. Direct conversion checks for a pending proposal without
locking it and aborts with ``pending_proposal_conflict``.

History ordering always uses ``sequence_number`` under the complaint row lock;
timestamps are never used to order lifecycle events.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.models.complaint import Complaint
from app.models.complaint_history import ComplaintHistory
from app.models.enums import (
    ComplaintStatus,
    UserRole,
    WorkOrderProposalStatus,
)
from app.models.work_order_proposal import WorkOrderProposal
from app.services.complaints.lifecycle import (
    READINESS_SOURCE_LIFECYCLE_V1,
    DiagnosticNotReadyError,
    InvalidLifecycleInputError,
    LifecycleActor,
    LifecycleEvent,
    LifecycleValidationError,
    ReadinessDecision,
    ReadinessMarker,
    ReadinessOperation,
    ReadinessProvenance,
    classify_readiness_provenance,
    coerce_actor,
    coerce_status,
    evaluate_readiness_provenance,
    validate_transition,
    validate_transition_fields,
)
from app.services.shared.authorization import AccessDeniedError

logger = logging.getLogger(__name__)

LEGACY_READINESS_BASIS = "no_lifecycle_marker_pre_cutoff_allowlisted"
CUSTOMER_CANCELLED_SUPERSESSION_REASON = "customer_cancelled"


@dataclass(frozen=True)
class ReadinessRecord:
    """Latest readiness provenance for the complaint's current ready state."""

    marker: ReadinessMarker | None
    has_lifecycle_marker_anywhere: bool
    entering_sequence_number: int | None = None


@dataclass(frozen=True)
class LifecycleTransition:
    """Outcome of one transactional lifecycle transition."""

    complaint: Complaint
    history: ComplaintHistory
    superseded_proposal_id: uuid.UUID | None = None
    classification: ReadinessProvenance | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)


async def lock_complaint(
    session: AsyncSession,
    complaint_id: uuid.UUID,
) -> Complaint:
    """Lock one complaint row and return the current, unexpired state."""

    result = await session.execute(
        select(Complaint)
        .where(Complaint.id == complaint_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    complaint = result.scalar_one_or_none()
    if complaint is None:
        raise AccessDeniedError("Complaint not found")
    return complaint


async def lock_complaint_row(
    session: AsyncSession,
    complaint_id: uuid.UUID,
) -> None:
    """Lock the complaint row without loading the full entity."""

    result = await session.execute(
        select(Complaint.id).where(Complaint.id == complaint_id).with_for_update()
    )
    if result.scalar_one_or_none() is None:
        raise AccessDeniedError("Complaint not found")


async def lock_proposal(
    session: AsyncSession,
    proposal_id: uuid.UUID,
) -> WorkOrderProposal:
    """Lock one proposal row. Callers must already hold higher-order locks."""

    result = await session.execute(
        select(WorkOrderProposal)
        .where(WorkOrderProposal.id == proposal_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    proposal = result.scalar_one_or_none()
    if proposal is None:
        raise AccessDeniedError("Work order proposal not found")
    return proposal


async def lock_pending_proposal(
    session: AsyncSession,
    complaint_id: uuid.UUID,
) -> WorkOrderProposal | None:
    """Lock the complaint's pending proposal, if any.

    The partial unique index allows at most one pending proposal per complaint.
    The caller must already hold the complaint row lock.
    """

    result = await session.execute(
        select(WorkOrderProposal)
        .where(
            WorkOrderProposal.complaint_id == complaint_id,
            WorkOrderProposal.status == WorkOrderProposalStatus.PENDING_APPROVAL,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def find_pending_proposal(
    session: AsyncSession,
    complaint_id: uuid.UUID,
) -> WorkOrderProposal | None:
    """Read the pending proposal without locking it.

    Direct conversion uses this under the complaint lock and aborts rather than
    mutating the proposal, so no proposal lock is acquired.
    """

    return await session.scalar(
        select(WorkOrderProposal).where(
            WorkOrderProposal.complaint_id == complaint_id,
            WorkOrderProposal.status == WorkOrderProposalStatus.PENDING_APPROVAL,
        )
    )


async def append_history(
    session: AsyncSession,
    *,
    complaint_id: uuid.UUID,
    event_type: str,
    from_status: ComplaintStatus | None,
    to_status: ComplaintStatus | None,
    changed_fields: dict[str, Any],
    actor_id: uuid.UUID | None,
) -> ComplaintHistory:
    """Append one history event under the complaint row lock."""

    await lock_complaint_row(session, complaint_id)
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


def supersession_reason_for(
    *,
    actor: LifecycleActor,
    target_status: ComplaintStatus,
) -> str:
    if actor is LifecycleActor.CUSTOMER and target_status is ComplaintStatus.CANCELLED:
        return CUSTOMER_CANCELLED_SUPERSESSION_REASON
    return f"complaint_status_changed:{target_status.value}"


def _event_type_for_transition(
    *,
    current_status: ComplaintStatus,
    target_status: ComplaintStatus,
    actor: LifecycleActor,
) -> str:
    if target_status is ComplaintStatus.CANCELLED:
        return LifecycleEvent.CANCELLED.value
    if target_status is ComplaintStatus.ESCALATED:
        return LifecycleEvent.ESCALATED.value
    if target_status is ComplaintStatus.CLOSED:
        return LifecycleEvent.CLOSED.value
    if target_status is ComplaintStatus.READY_FOR_WORK_ORDER:
        return LifecycleEvent.READY_FOR_WORK_ORDER.value
    if target_status is ComplaintStatus.CONVERTED:
        return LifecycleEvent.CONVERTED.value
    if target_status is ComplaintStatus.AWAITING_CUSTOMER:
        return LifecycleEvent.CLARIFICATION_REQUESTED.value
    if target_status is ComplaintStatus.ANALYZING:
        if actor is LifecycleActor.CUSTOMER:
            return LifecycleEvent.CUSTOMER_RESPONDED.value
        if current_status in (
            ComplaintStatus.READY_FOR_WORK_ORDER,
            ComplaintStatus.ESCALATED,
        ):
            return LifecycleEvent.REOPENED.value
        return LifecycleEvent.INVESTIGATION_REQUESTED.value
    return LifecycleEvent.UPDATED.value


def _normalize_event_type(
    event_type: LifecycleEvent | str | None,
    *,
    current_status: ComplaintStatus,
    target_status: ComplaintStatus,
    actor: LifecycleActor,
) -> str:
    if event_type is None:
        return _event_type_for_transition(
            current_status=current_status,
            target_status=target_status,
            actor=actor,
        )
    value = event_type.value if isinstance(event_type, LifecycleEvent) else event_type
    if not isinstance(value, str):
        raise InvalidLifecycleInputError(
            f"Lifecycle event type must be a string, got {type(value).__name__}"
        )
    normalized = value.strip()
    if not normalized:
        raise LifecycleValidationError("Lifecycle event type must not be blank.")
    if len(normalized) > 40:
        raise LifecycleValidationError(
            "Lifecycle event type must fit the 40-character history column."
        )
    return normalized


def _readiness_changed_fields(marker: ReadinessMarker) -> dict[str, Any]:
    return {
        "readiness_source": READINESS_SOURCE_LIFECYCLE_V1,
        "diagnostic_workflow_run_id": marker.diagnostic_workflow_run_id,
        "diagnostic_context_fingerprint": (marker.diagnostic_context_fingerprint),
        "diagnostic_context_fingerprint_version": (
            marker.diagnostic_context_fingerprint_version
        ),
        "diagnostic_evidence_revision": marker.diagnostic_evidence_revision,
    }


async def supersede_pending_proposal(
    session: AsyncSession,
    *,
    proposal: WorkOrderProposal,
    actor_id: uuid.UUID | None,
    reason: str,
) -> bool:
    """Invalidate a pending proposal without writing human review fields."""

    if proposal.status is not WorkOrderProposalStatus.PENDING_APPROVAL:
        return False
    proposal.status = WorkOrderProposalStatus.SUPERSEDED
    proposal.superseded_at = datetime.now(UTC)
    proposal.superseded_by_id = actor_id
    proposal.supersession_reason = reason
    await session.flush()
    return True


async def transition_locked_complaint(
    session: AsyncSession,
    *,
    complaint: Complaint,
    target_status: ComplaintStatus | str,
    actor: LifecycleActor | UserRole | str,
    actor_id: uuid.UUID | None,
    expected_status: ComplaintStatus | str | None = None,
    fields: Mapping[str, object] | None = None,
    event_type: LifecycleEvent | str | None = None,
    changed_fields: Mapping[str, Any] | None = None,
    readiness_marker: ReadinessMarker | None = None,
) -> LifecycleTransition:
    """Apply one lifecycle transition to an already locked complaint.

    The caller must hold the complaint row lock for the surrounding
    transaction. Readiness provenance is server-owned: a caller may pass a
    structured :class:`ReadinessMarker` resolved from persistence, never raw
    client fields.
    """

    target = coerce_status(target_status)
    normalized_actor = coerce_actor(actor)
    request_fields = dict(fields or {})

    validate_transition(
        complaint.status,
        target,
        normalized_actor,
        expected_status=expected_status,
    )
    validate_transition_fields(target, request_fields)

    if target is ComplaintStatus.READY_FOR_WORK_ORDER:
        if (
            readiness_marker is None
            or not readiness_marker.is_complete_lifecycle_provenance()
        ):
            raise DiagnosticNotReadyError(
                "Server-owned lifecycle readiness provenance is required."
            )
    elif readiness_marker is not None:
        raise LifecycleValidationError(
            "Readiness provenance is only valid for readiness confirmation."
        )

    previous_status = complaint.status
    resolved_event_type = _normalize_event_type(
        event_type,
        current_status=previous_status,
        target_status=target,
        actor=normalized_actor,
    )

    history_fields: dict[str, Any] = dict(changed_fields or {})
    for key in (
        "reason",
        "reason_code",
        "resolution_code",
        "resolution_summary",
        "clarification_message_id",
    ):
        value = request_fields.get(key)
        if value is not None:
            history_fields[key] = value

    superseded_proposal_id: uuid.UUID | None = None
    if (
        previous_status is ComplaintStatus.READY_FOR_WORK_ORDER
        and target is not ComplaintStatus.CONVERTED
    ):
        pending = await lock_pending_proposal(session, complaint.id)
        if pending is not None:
            reason = supersession_reason_for(
                actor=normalized_actor,
                target_status=target,
            )
            if await supersede_pending_proposal(
                session,
                proposal=pending,
                actor_id=actor_id,
                reason=reason,
            ):
                superseded_proposal_id = pending.id
                history_fields["superseded_proposal_id"] = str(pending.id)
                history_fields["supersession_reason"] = reason

    if target is ComplaintStatus.READY_FOR_WORK_ORDER and readiness_marker is not None:
        history_fields.update(_readiness_changed_fields(readiness_marker))

    history_fields["status"] = {
        "from": previous_status.value,
        "to": target.value,
    }

    complaint.status = target
    history = await append_history(
        session,
        complaint_id=complaint.id,
        event_type=resolved_event_type,
        from_status=previous_status,
        to_status=target,
        changed_fields=history_fields,
        actor_id=actor_id,
    )
    await session.flush()

    return LifecycleTransition(
        complaint=complaint,
        history=history,
        superseded_proposal_id=superseded_proposal_id,
    )


async def transition_complaint(
    session: AsyncSession,
    *,
    complaint_id: uuid.UUID,
    target_status: ComplaintStatus | str,
    actor: LifecycleActor | UserRole | str,
    actor_id: uuid.UUID | None,
    expected_status: ComplaintStatus | str | None = None,
    fields: Mapping[str, object] | None = None,
    event_type: LifecycleEvent | str | None = None,
    changed_fields: Mapping[str, Any] | None = None,
    readiness_marker: ReadinessMarker | None = None,
) -> LifecycleTransition:
    """Lock a complaint and apply one lifecycle transition."""

    complaint = await lock_complaint(session, complaint_id)
    return await transition_locked_complaint(
        session,
        complaint=complaint,
        target_status=target_status,
        actor=actor,
        actor_id=actor_id,
        expected_status=expected_status,
        fields=fields,
        event_type=event_type,
        changed_fields=changed_fields,
        readiness_marker=readiness_marker,
    )


async def cancel_complaint(
    session: AsyncSession,
    *,
    complaint_id: uuid.UUID,
    actor: LifecycleActor | UserRole | str,
    actor_id: uuid.UUID | None,
    expected_status: ComplaintStatus | str | None = None,
    reason: str | None = None,
) -> LifecycleTransition:
    """Cancel a complaint through the lifecycle policy and supersede a proposal."""

    fields: dict[str, object] = {}
    if reason is not None:
        fields["reason"] = reason
    return await transition_complaint(
        session,
        complaint_id=complaint_id,
        target_status=ComplaintStatus.CANCELLED,
        actor=actor,
        actor_id=actor_id,
        expected_status=expected_status,
        fields=fields,
    )


async def convert_locked_complaint(
    session: AsyncSession,
    *,
    complaint: Complaint,
    actor_id: uuid.UUID,
    changed_fields: Mapping[str, Any] | None = None,
) -> LifecycleTransition:
    """Record system conversion for an already locked complaint."""

    return await transition_locked_complaint(
        session,
        complaint=complaint,
        target_status=ComplaintStatus.CONVERTED,
        actor=LifecycleActor.SYSTEM,
        actor_id=actor_id,
        event_type=LifecycleEvent.CONVERTED,
        changed_fields=changed_fields,
    )


# Readiness provenance -----------------------------------------------------


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _marker_from_changed_fields(
    changed_fields: Mapping[str, Any] | None,
) -> ReadinessMarker:
    source = changed_fields if isinstance(changed_fields, Mapping) else {}

    run_id = source.get("diagnostic_workflow_run_id")
    fingerprint = source.get("diagnostic_context_fingerprint")
    readiness_source = source.get("readiness_source")

    return ReadinessMarker(
        readiness_source=(
            readiness_source if isinstance(readiness_source, str) else None
        ),
        diagnostic_workflow_run_id=(str(run_id) if run_id is not None else None),
        diagnostic_context_fingerprint=(
            fingerprint if isinstance(fingerprint, str) else None
        ),
        diagnostic_context_fingerprint_version=_optional_int(
            source.get("diagnostic_context_fingerprint_version")
        ),
        diagnostic_evidence_revision=_optional_int(
            source.get("diagnostic_evidence_revision")
        ),
    )


async def load_readiness_record(
    session: AsyncSession,
    complaint_id: uuid.UUID,
) -> ReadinessRecord:
    """Read the latest readiness record and marker presence.

    This is an unlocked read. Conversion and approval call it while holding the
    complaint row lock, which prevents a new status writer from racing it.
    """

    latest = await session.scalar(
        select(ComplaintHistory)
        .where(
            ComplaintHistory.complaint_id == complaint_id,
            ComplaintHistory.to_status == ComplaintStatus.READY_FOR_WORK_ORDER,
        )
        .order_by(ComplaintHistory.sequence_number.desc())
        .limit(1)
    )
    marker = (
        _marker_from_changed_fields(latest.changed_fields)
        if latest is not None
        else None
    )

    marker_count = await session.scalar(
        select(func.count(ComplaintHistory.id)).where(
            ComplaintHistory.complaint_id == complaint_id,
            ComplaintHistory.changed_fields["readiness_source"].astext
            == READINESS_SOURCE_LIFECYCLE_V1,
        )
    )

    return ReadinessRecord(
        marker=marker,
        has_lifecycle_marker_anywhere=bool(marker_count),
        entering_sequence_number=(
            latest.sequence_number if latest is not None else None
        ),
    )


def _legacy_settings(
    settings: Settings | None,
) -> Settings:
    return settings or get_settings()


async def classify_readiness(
    session: AsyncSession,
    complaint: Complaint,
    *,
    settings: Settings | None = None,
) -> tuple[ReadinessRecord, ReadinessProvenance]:
    """Classify readiness provenance using deployment configuration."""

    resolved = _legacy_settings(settings)
    record = await load_readiness_record(session, complaint.id)
    cutoff = resolved.lifecycle_readiness_enforced_at
    provenance = classify_readiness_provenance(
        record.marker,
        has_lifecycle_marker_anywhere=record.has_lifecycle_marker_anywhere,
        legacy_allowlisted=(complaint.id in resolved.lifecycle_legacy_ready_id_set),
        created_before_enforcement_cutoff=(
            cutoff is not None and complaint.created_at < cutoff
        ),
    )
    return record, provenance


async def evaluate_readiness(
    session: AsyncSession,
    complaint: Complaint,
    *,
    operation: ReadinessOperation | str,
    settings: Settings | None = None,
) -> tuple[ReadinessRecord, ReadinessDecision]:
    """Classify readiness and return the operation's policy decision."""

    record, provenance = await classify_readiness(
        session,
        complaint,
        settings=settings,
    )
    return record, evaluate_readiness_provenance(provenance, operation)


def legacy_readiness_audit_fields() -> dict[str, Any]:
    """Audit fields written into ``converted`` history by the legacy exception."""

    return {
        "legacy_readiness_exception": True,
        "legacy_readiness_basis": LEGACY_READINESS_BASIS,
        "legacy_readiness_diagnostic": None,
    }


def log_legacy_readiness_exception(
    *,
    complaint_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    operation: ReadinessOperation | str,
) -> None:
    logger.info(
        "Legacy readiness exception used",
        extra={
            "event": "legacy_readiness_exception_used",
            "complaint_id": str(complaint_id),
            "actor_id": str(actor_id) if actor_id is not None else None,
            "operation": (
                operation.value
                if isinstance(operation, ReadinessOperation)
                else operation
            ),
            "legacy_readiness_basis": LEGACY_READINESS_BASIS,
        },
    )


__all__ = [
    "CUSTOMER_CANCELLED_SUPERSESSION_REASON",
    "LEGACY_READINESS_BASIS",
    "LifecycleTransition",
    "ReadinessRecord",
    "append_history",
    "cancel_complaint",
    "classify_readiness",
    "convert_locked_complaint",
    "evaluate_readiness",
    "find_pending_proposal",
    "legacy_readiness_audit_fields",
    "load_readiness_record",
    "lock_complaint",
    "lock_complaint_row",
    "lock_pending_proposal",
    "lock_proposal",
    "log_legacy_readiness_exception",
    "supersede_pending_proposal",
    "supersession_reason_for",
    "transition_complaint",
    "transition_locked_complaint",
]
