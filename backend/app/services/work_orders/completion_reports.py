from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.completion_report import CompletionReport
from app.models.enums import (
    AssignmentStatus,
    EvidenceStatus,
    WorkOrderStatus,
)
from app.models.service_record import ServiceRecord
from app.models.technician_assignment import TechnicianAssignment
from app.models.user import User
from app.schemas.work_orders.completion_report import (
    CompletionReportCreate,
    CompletionReportUpdate,
)
from app.services.shared.authorization import (
    AccessDeniedError,
    get_completion_report_for_user,
    get_work_order_for_user,
    is_admin,
    is_technician,
    scope_completion_reports_for_user,
)

COMPLETION_REPORT_WORK_ORDER_STATUSES = frozenset(
    {
        WorkOrderStatus.ACCEPTED,
        WorkOrderStatus.IN_PROGRESS,
        WorkOrderStatus.AWAITING_PARTS,
        WorkOrderStatus.PENDING_VERIFICATION,
    }
)

ADMIN_EVIDENCE_TRANSITIONS: dict[
    EvidenceStatus, frozenset[EvidenceStatus]
] = {
    EvidenceStatus.PENDING: frozenset(
        {EvidenceStatus.VERIFIED, EvidenceStatus.REJECTED}
    ),
    EvidenceStatus.REJECTED: frozenset(
        {EvidenceStatus.PENDING, EvidenceStatus.VERIFIED}
    ),
    EvidenceStatus.VERIFIED: frozenset(),
}

COMPLETION_REPORT_WORK_ORDER_UNIQUE = (
    "uq_completion_reports_work_order_id"
)
COMPLETION_REPORT_SERVICE_RECORD_FK = (
    "fk_completion_reports_service_record_work_order"
)


class CompletionReportStateError(Exception):
    """Raised when a report cannot change in its current state."""


class CompletionReportConflictError(Exception):
    """Raised when a work order already has a completion report."""


class CompletionReportAssociationError(Exception):
    """Raised when a service record does not belong to the work order."""


class CompletionReportPermissionError(Exception):
    """Raised when a technician attempts an administrator-only change."""


def _constraint_name(exc: IntegrityError) -> str | None:
    original = exc.orig
    diagnostics = getattr(original, "diag", None)
    return (
        getattr(original, "constraint_name", None)
        or getattr(diagnostics, "constraint_name", None)
        or None
    )


def is_completion_report_integrity_conflict(
    exc: IntegrityError,
) -> bool:
    """Return True for expected report uniqueness/association violations."""
    name = _constraint_name(exc)
    if name in {
        COMPLETION_REPORT_WORK_ORDER_UNIQUE,
        COMPLETION_REPORT_SERVICE_RECORD_FK,
    }:
        return True

    text = str(exc.orig)
    return (
        COMPLETION_REPORT_WORK_ORDER_UNIQUE in text
        or COMPLETION_REPORT_SERVICE_RECORD_FK in text
    )


async def list_completion_reports(
    session: AsyncSession,
    user: User,
    *,
    work_order_id: uuid.UUID | None,
    service_record_id: uuid.UUID | None,
    evidence_status: EvidenceStatus | None,
    limit: int,
    offset: int,
) -> tuple[list[CompletionReport], int]:
    filters = []
    if work_order_id is not None:
        filters.append(CompletionReport.work_order_id == work_order_id)
    if service_record_id is not None:
        filters.append(
            CompletionReport.service_record_id == service_record_id
        )
    if evidence_status is not None:
        filters.append(
            CompletionReport.evidence_status == evidence_status
        )

    scoped = scope_completion_reports_for_user(user).where(*filters)
    total = await session.scalar(
        select(func.count()).select_from(scoped.subquery())
    )
    statement = (
        scoped.order_by(
            CompletionReport.submitted_at.desc(),
            CompletionReport.id.desc(),
        )
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(statement)
    return list(result.scalars().all()), int(total or 0)


async def get_completion_report(
    session: AsyncSession,
    user: User,
    completion_report_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> CompletionReport:
    return await get_completion_report_for_user(
        session,
        user,
        completion_report_id,
        for_update=for_update,
    )


async def _load_service_record(
    session: AsyncSession,
    *,
    service_record_id: uuid.UUID,
    work_order_id: uuid.UUID,
) -> ServiceRecord | None:
    result = await session.execute(
        select(ServiceRecord)
        .where(
            ServiceRecord.id == service_record_id,
            ServiceRecord.work_order_id == work_order_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def _require_accepted_assignment(
    session: AsyncSession,
    *,
    work_order_id: uuid.UUID,
    technician_id: uuid.UUID,
) -> None:
    assignment_id = await session.scalar(
        select(TechnicianAssignment.id)
        .where(
            TechnicianAssignment.work_order_id == work_order_id,
            TechnicianAssignment.technician_id == technician_id,
            TechnicianAssignment.assignment_status
            == AssignmentStatus.ACCEPTED,
        )
        .with_for_update()
    )
    if assignment_id is None:
        raise AccessDeniedError("Work order not found")


def _require_work_performed(service_record: ServiceRecord) -> None:
    if (
        not service_record.work_performed
        or not service_record.work_performed.strip()
    ):
        raise CompletionReportStateError(
            "The associated service record must document work performed"
        )


async def create_completion_report(
    session: AsyncSession,
    *,
    user: User,
    work_order_id: uuid.UUID,
    data: CompletionReportCreate,
) -> CompletionReport:
    if not (is_admin(user) or is_technician(user)):
        raise AccessDeniedError("Work order not found")

    work_order = await get_work_order_for_user(
        session,
        user,
        work_order_id,
        for_update=True,
    )

    if work_order.status not in COMPLETION_REPORT_WORK_ORDER_STATUSES:
        raise CompletionReportStateError(
            "Work order is not in a state that permits completion reporting"
        )

    service_record = await _load_service_record(
        session,
        service_record_id=data.service_record_id,
        work_order_id=work_order.id,
    )
    if service_record is None:
        raise CompletionReportAssociationError(
            "Service record does not belong to this work order"
        )
    _require_work_performed(service_record)

    if is_technician(user):
        technician = user.technician
        if technician is None:
            raise AccessDeniedError("Work order not found")
        await _require_accepted_assignment(
            session,
            work_order_id=work_order.id,
            technician_id=technician.id,
        )
        if service_record.technician_id != technician.id:
            raise AccessDeniedError("Service record not found")

    existing_report = await session.scalar(
        select(CompletionReport.id).where(
            CompletionReport.work_order_id == work_order.id
        )
    )
    if existing_report is not None:
        raise CompletionReportConflictError(
            "A completion report already exists for this work order"
        )

    report = CompletionReport(
        work_order_id=work_order.id,
        service_record_id=service_record.id,
        summary=data.summary,
        evidence_status=EvidenceStatus.PENDING,
    )
    session.add(report)
    await session.flush()
    return report


async def _update_as_admin(
    session: AsyncSession,
    report: CompletionReport,
    data: CompletionReportUpdate,
) -> CompletionReport:
    target_status = data.evidence_status
    current_status = report.evidence_status

    if current_status is EvidenceStatus.VERIFIED:
        raise CompletionReportStateError(
            "Verified completion reports are immutable"
        )

    if target_status is not None:
        allowed = ADMIN_EVIDENCE_TRANSITIONS.get(
            current_status,
            frozenset(),
        )
        if target_status not in allowed:
            raise CompletionReportStateError(
                "Completion evidence status transition is not permitted"
            )

    if "summary" in data.model_fields_set:
        assert data.summary is not None
        report.summary = data.summary

    if "verification_notes" in data.model_fields_set:
        report.verification_notes = data.verification_notes

    if target_status is not None:
        report.evidence_status = target_status
        if target_status is EvidenceStatus.VERIFIED:
            report.verified_at = datetime.now(UTC)
        else:
            report.verified_at = None

    await session.flush()
    return report


async def _update_as_technician(
    session: AsyncSession,
    user: User,
    report: CompletionReport,
    data: CompletionReportUpdate,
) -> CompletionReport:
    if "evidence_status" in data.model_fields_set:
        raise CompletionReportPermissionError(
            "Only administrators can change evidence status"
        )
    if "verification_notes" in data.model_fields_set:
        raise CompletionReportPermissionError(
            "Only administrators can change verification notes"
        )

    technician = user.technician
    if technician is None:
        raise AccessDeniedError("Completion report not found")

    service_record = await session.get(
        ServiceRecord,
        report.service_record_id,
    ) if report.service_record_id is not None else None
    if (
        service_record is None
        or service_record.technician_id != technician.id
    ):
        raise AccessDeniedError("Completion report not found")

    work_order = await get_work_order_for_user(
        session,
        user,
        report.work_order_id,
        for_update=True,
    )
    if work_order.status not in COMPLETION_REPORT_WORK_ORDER_STATUSES:
        raise CompletionReportStateError(
            "Completion report is not editable in the current work-order "
            "state"
        )
    if report.evidence_status is not EvidenceStatus.PENDING:
        raise CompletionReportStateError(
            "Only pending completion reports can be edited"
        )

    assert data.summary is not None
    report.summary = data.summary
    await session.flush()
    return report


async def update_completion_report(
    session: AsyncSession,
    *,
    user: User,
    completion_report_id: uuid.UUID,
    data: CompletionReportUpdate,
) -> CompletionReport:
    report = await get_completion_report_for_user(
        session,
        user,
        completion_report_id,
        for_update=True,
    )

    if is_admin(user):
        return await _update_as_admin(session, report, data)
    if is_technician(user):
        return await _update_as_technician(session, user, report, data)

    raise AccessDeniedError("Completion report not found")
