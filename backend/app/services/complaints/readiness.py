"""Shared readiness validation for confirmation, conversion, and approval.

Every caller must already hold the complaint row lock. The validator then
acquires the readiness diagnostic ``workflow_runs`` row ``FOR SHARE`` (lock
hierarchy position 2) before any work order, assignment, proposal, status, or
history write. It never mutates complaint or proposal state on failure.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.complaint import Complaint
from app.models.enums import WorkflowRunStatus, WorkflowRunType
from app.models.equipment import Equipment
from app.models.work_order import WorkOrder
from app.models.workflow_run import WorkflowRun
from app.schemas.diagnostics.diagnostic import DiagnosticStatus
from app.services.complaints import lifecycle_service
from app.services.complaints.lifecycle import (
    READINESS_SOURCE_LIFECYCLE_V1,
    SUPPORTED_CONTEXT_FINGERPRINT_VERSIONS,
    DiagnosticNotReadyError,
    DiagnosticStaleError,
    EquipmentRequiredError,
    ReadinessMarker,
    ReadinessOperation,
    ReadinessProvenance,
    evaluate_readiness_provenance,
)
from app.services.diagnostics.readiness_context import (
    compute_diagnostic_context,
)

PRE_CONVERSION_PHASE = "pre_conversion"


@dataclass(frozen=True)
class StoredDiagnosticContext:
    """The fingerprint values persisted on a diagnostic workflow run."""

    fingerprint: str
    fingerprint_version: int
    evidence_revision: int


@dataclass(frozen=True)
class ReadinessValidation:
    """Outcome of the shared readiness gate for one conversion/approval."""

    provenance: ReadinessProvenance
    run: WorkflowRun | None
    marker: ReadinessMarker | None
    uses_legacy_exception: bool
    audit_fields: dict[str, Any] = field(default_factory=dict)

    @property
    def diagnostic_workflow_run_id(self) -> uuid.UUID | None:
        return self.run.id if self.run is not None else None


def _is_sha256_hex(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    return all(character in "0123456789abcdefABCDEF" for character in value)


def _stored_context(run: WorkflowRun) -> StoredDiagnosticContext:
    payload = run.input_payload if isinstance(run.input_payload, dict) else {}
    fingerprint = payload.get("context_fingerprint")
    version = payload.get("context_fingerprint_version")
    evidence_revision = payload.get("evidence_revision")

    if (
        not isinstance(fingerprint, str)
        or not _is_sha256_hex(fingerprint)
        or not isinstance(version, int)
        or isinstance(version, bool)
        or version not in SUPPORTED_CONTEXT_FINGERPRINT_VERSIONS
        or not isinstance(evidence_revision, int)
        or isinstance(evidence_revision, bool)
        or evidence_revision < 0
    ):
        raise DiagnosticStaleError(
            "Diagnostic evidence has no supported context fingerprint."
        )

    return StoredDiagnosticContext(
        fingerprint=fingerprint,
        fingerprint_version=version,
        evidence_revision=evidence_revision,
    )


def _is_pre_conversion(run: WorkflowRun) -> bool:
    """Return True only for an explicitly marked pre-conversion run.

    Missing, unknown, non-string, and post-conversion phase metadata all fail
    closed. There is no fallback that treats absent metadata as pre-conversion,
    because the legacy compatibility exception is decided from complaint
    history, not from an untagged diagnostic run.
    """

    payload = run.input_payload if isinstance(run.input_payload, dict) else {}
    phase = payload.get("lifecycle_phase")
    if phase != PRE_CONVERSION_PHASE:
        return False
    return payload.get("readiness_eligible") is not False


def _validate_diagnostic_run(
    run: WorkflowRun,
    complaint: Complaint,
) -> StoredDiagnosticContext:
    if run.complaint_id != complaint.id:
        raise DiagnosticNotReadyError(
            "The diagnostic does not belong to this complaint."
        )
    if run.workflow_type is not WorkflowRunType.DIAGNOSTIC_INVESTIGATION:
        raise DiagnosticNotReadyError(
            "The workflow run is not a diagnostic investigation."
        )
    if run.status is not WorkflowRunStatus.COMPLETED:
        raise DiagnosticNotReadyError(
            "The diagnostic investigation is not completed."
        )
    if not _is_pre_conversion(run):
        raise DiagnosticNotReadyError(
            "The diagnostic is not eligible for pre-conversion readiness."
        )

    result = run.result_payload if isinstance(run.result_payload, dict) else {}
    if result.get("status") != DiagnosticStatus.DIAGNOSED.value:
        raise DiagnosticNotReadyError(
            "The diagnostic outcome does not support readiness."
        )
    if result.get("requires_escalation") is not False:
        raise DiagnosticNotReadyError(
            "The diagnostic requires escalation and cannot confirm readiness."
        )

    return _stored_context(run)


async def _load_equipment(
    session: AsyncSession,
    complaint: Complaint,
    *,
    lock: bool,
) -> Equipment:
    if complaint.equipment_id is None:
        raise EquipmentRequiredError(
            "Readiness requires an equipment association."
        )

    statement = select(Equipment).where(
        Equipment.id == complaint.equipment_id,
        Equipment.customer_id == complaint.customer_id,
    )
    if lock:
        statement = statement.with_for_update(read=True)
    equipment = (await session.execute(statement)).scalar_one_or_none()
    if equipment is None:
        raise EquipmentRequiredError(
            "The complaint equipment is unavailable."
        )
    return equipment


async def _ensure_no_work_order(
    session: AsyncSession,
    complaint_id: uuid.UUID,
) -> None:
    existing = await session.scalar(
        select(WorkOrder.id).where(WorkOrder.complaint_id == complaint_id)
    )
    if existing is not None:
        raise DiagnosticNotReadyError(
            "A work order already exists for this complaint."
        )


def _latest_pre_conversion_run_statement(complaint_id: uuid.UUID):
    return (
        select(WorkflowRun)
        .where(
            WorkflowRun.complaint_id == complaint_id,
            WorkflowRun.workflow_type
            == WorkflowRunType.DIAGNOSTIC_INVESTIGATION,
            WorkflowRun.status == WorkflowRunStatus.COMPLETED,
        )
        .order_by(
            func.coalesce(
                WorkflowRun.finished_at,
                WorkflowRun.started_at,
            ).desc(),
            WorkflowRun.id.desc(),
        )
        .limit(1)
    )


async def _lock_run(
    session: AsyncSession,
    run_id: uuid.UUID,
) -> WorkflowRun:
    run = (
        await session.execute(
            select(WorkflowRun)
            .where(WorkflowRun.id == run_id)
            .with_for_update(read=True)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if run is None:
        raise DiagnosticNotReadyError("The diagnostic run is unavailable.")
    return run


async def _resolve_readiness_run(
    session: AsyncSession,
    complaint: Complaint,
    requested_run_id: uuid.UUID | None,
) -> tuple[WorkflowRun, StoredDiagnosticContext]:
    latest_id = await session.scalar(
        _latest_pre_conversion_run_statement(complaint.id).with_only_columns(
            WorkflowRun.id
        )
    )
    if latest_id is None:
        raise DiagnosticNotReadyError(
            "A completed pre-conversion diagnostic is required."
        )
    if requested_run_id is not None and requested_run_id != latest_id:
        raise DiagnosticNotReadyError(
            "The supplied diagnostic is not the latest qualifying run."
        )

    run = await _lock_run(session, latest_id)
    stored = _validate_diagnostic_run(run, complaint)
    return run, stored


async def _ensure_current_fingerprint(
    session: AsyncSession,
    complaint: Complaint,
    equipment: Equipment,
    stored: StoredDiagnosticContext,
) -> None:
    current = await compute_diagnostic_context(
        session,
        complaint,
        equipment,
        lock=True,
    )
    if (
        current.fingerprint != stored.fingerprint
        or current.fingerprint_version != stored.fingerprint_version
        or current.evidence_revision != stored.evidence_revision
    ):
        raise DiagnosticStaleError(
            "Diagnostic evidence no longer matches the complaint context."
        )


def _lifecycle_audit_fields(
    run: WorkflowRun,
    stored: StoredDiagnosticContext,
) -> dict[str, Any]:
    return {
        "readiness_source": READINESS_SOURCE_LIFECYCLE_V1,
        "diagnostic_workflow_run_id": str(run.id),
        "diagnostic_context_fingerprint": stored.fingerprint,
        "diagnostic_context_fingerprint_version": (
            stored.fingerprint_version
        ),
        "diagnostic_evidence_revision": stored.evidence_revision,
        "readiness_revalidated": True,
    }


async def confirm_readiness(
    session: AsyncSession,
    complaint: Complaint,
    *,
    requested_run_id: uuid.UUID | None = None,
) -> ReadinessMarker:
    """Validate a new readiness confirmation and return its provenance marker."""

    await _ensure_no_work_order(session, complaint.id)
    equipment = await _load_equipment(session, complaint, lock=True)
    run, stored = await _resolve_readiness_run(
        session,
        complaint,
        requested_run_id,
    )
    await _ensure_current_fingerprint(session, complaint, equipment, stored)
    return ReadinessMarker(
        readiness_source=READINESS_SOURCE_LIFECYCLE_V1,
        diagnostic_workflow_run_id=str(run.id),
        diagnostic_context_fingerprint=stored.fingerprint,
        diagnostic_context_fingerprint_version=stored.fingerprint_version,
        diagnostic_evidence_revision=stored.evidence_revision,
    )


async def validate_readiness_for_operation(
    session: AsyncSession,
    complaint: Complaint,
    *,
    operation: ReadinessOperation | str,
    actor_id: uuid.UUID | None = None,
    settings: Settings | None = None,
) -> ReadinessValidation:
    """Revalidate readiness before conversion or proposal approval."""

    record, provenance = await lifecycle_service.classify_readiness(
        session,
        complaint,
        settings=settings,
    )
    decision = evaluate_readiness_provenance(provenance, operation)

    if decision.uses_legacy_exception:
        lifecycle_service.log_legacy_readiness_exception(
            complaint_id=complaint.id,
            actor_id=actor_id,
            operation=operation,
        )
        return ReadinessValidation(
            provenance=ReadinessProvenance.LEGACY_ELIGIBLE,
            run=None,
            marker=None,
            uses_legacy_exception=True,
            audit_fields=lifecycle_service.legacy_readiness_audit_fields(),
        )

    marker = record.marker
    if marker is None or not marker.is_complete_lifecycle_provenance():
        raise DiagnosticStaleError(
            "Lifecycle readiness provenance is missing or invalid."
        )

    try:
        run_id = uuid.UUID(str(marker.diagnostic_workflow_run_id))
    except (TypeError, ValueError) as exc:
        raise DiagnosticStaleError(
            "Lifecycle readiness provenance has an invalid run identifier."
        ) from exc

    run = await _lock_run(session, run_id)
    stored = _validate_diagnostic_run(run, complaint)
    if (
        marker.diagnostic_context_fingerprint != stored.fingerprint
        or marker.diagnostic_context_fingerprint_version
        != stored.fingerprint_version
        or marker.diagnostic_evidence_revision
        != stored.evidence_revision
    ):
        raise DiagnosticStaleError(
            "Lifecycle readiness provenance no longer matches the diagnostic."
        )

    equipment = await _load_equipment(session, complaint, lock=True)
    await _ensure_current_fingerprint(session, complaint, equipment, stored)
    return ReadinessValidation(
        provenance=ReadinessProvenance.LIFECYCLE,
        run=run,
        marker=marker,
        uses_legacy_exception=False,
        audit_fields=_lifecycle_audit_fields(run, stored),
    )


__all__ = [
    "PRE_CONVERSION_PHASE",
    "ReadinessValidation",
    "StoredDiagnosticContext",
    "confirm_readiness",
    "validate_readiness_for_operation",
]
