"""Deterministic complaint-context fingerprint used by readiness.

The fingerprint is captured by the diagnostic worker during the ``prepare``
phase and recomputed under the complaint lock at readiness confirmation,
direct conversion, and proposal approval. It therefore covers the complaint
text, equipment facts, and the evidence the diagnostic actually read.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.complaint import Complaint
from app.models.complaint_history import ComplaintHistory
from app.models.document import Document
from app.models.enums import IngestionStatus
from app.models.equipment import Equipment
from app.models.service_record import ServiceRecord
from app.services.complaints.lifecycle import LifecycleEvent
from app.services.shared.canonical import (
    canonical_digest,
    canonical_symptoms,
    digest_records,
)

DIAGNOSTIC_CONTEXT_FINGERPRINT_VERSION = 1

# Only evidence-bearing complaint fields are included. Lifecycle status is
# deliberately excluded so confirming readiness cannot self-invalidate the
# diagnostic that justified it.
DIAGNOSTIC_CONTEXT_FINGERPRINT_FIELDS: tuple[str, ...] = (
    "description",
    "reported_error_code",
    "reported_symptoms",
    "priority",
    "equipment_id",
    "equipment.manufacturer",
    "equipment.model",
    "equipment.equipment_type",
    "evidence_revision",
    "service_history_digest",
    "knowledge_corpus_digest",
)

EVIDENCE_REVISION_EVENT_TYPES: tuple[str, ...] = (
    LifecycleEvent.UPDATED.value,
    LifecycleEvent.CLARIFICATION_REQUESTED.value,
    LifecycleEvent.CUSTOMER_RESPONDED.value,
    LifecycleEvent.INVESTIGATION_REQUESTED.value,
)


@dataclass(frozen=True)
class DiagnosticContext:
    """Current fingerprint plus the values it was computed from."""

    fingerprint: str
    fingerprint_version: int
    evidence_revision: int
    service_history_digest: str
    knowledge_corpus_digest: str


async def compute_evidence_revision(
    session: AsyncSession,
    complaint_id: uuid.UUID,
) -> int:
    """Return the maximum information-bearing history sequence, or zero."""

    value = await session.scalar(
        select(func.max(ComplaintHistory.sequence_number)).where(
            ComplaintHistory.complaint_id == complaint_id,
            ComplaintHistory.event_type.in_(EVIDENCE_REVISION_EVENT_TYPES),
        )
    )
    return int(value or 0)


async def _service_history_payload(
    session: AsyncSession,
    equipment_id: uuid.UUID | None,
    *,
    lock: bool,
) -> list[dict[str, Any]]:
    if equipment_id is None:
        return []

    limit = get_settings().diagnostic_max_service_records
    statement = (
        select(ServiceRecord)
        .where(ServiceRecord.equipment_id == equipment_id)
        .order_by(
            ServiceRecord.recorded_at.desc(),
            ServiceRecord.id.desc(),
        )
        .limit(limit)
    )
    if lock:
        statement = statement.with_for_update(read=True)
    records = list((await session.execute(statement)).scalars().all())
    return [
        {
            "id": str(record.id),
            "recorded_at": record.recorded_at.isoformat(),
            "findings": record.findings,
            "work_performed": record.work_performed,
            "parts_used": record.parts_used,
        }
        for record in records
    ]


async def _knowledge_corpus_payload(
    session: AsyncSession,
    equipment: Equipment | None,
    *,
    lock: bool,
) -> list[dict[str, Any]]:
    statement = select(Document).where(
        Document.is_active.is_(True),
        Document.ingestion_status == IngestionStatus.READY,
    )
    if equipment is not None:
        statement = statement.where(
            func.lower(Document.manufacturer) == equipment.manufacturer.lower(),
            func.lower(Document.model) == equipment.model.lower(),
        )
    statement = statement.order_by(Document.id.asc())
    if lock:
        statement = statement.with_for_update(read=True)
    documents = list((await session.execute(statement)).scalars().all())
    return [
        {
            "id": str(document.id),
            "document_name": document.document_name,
            "version": document.version,
            "checksum_sha256": document.checksum_sha256,
            "embedding_model": document.embedding_model,
        }
        for document in documents
    ]


def diagnostic_context_payload(
    complaint: Complaint,
    equipment: Equipment | None,
    *,
    evidence_revision: int,
    service_history_digest: str,
    knowledge_corpus_digest: str,
) -> dict[str, Any]:
    """Build the canonical payload that is hashed for readiness."""

    return {
        "version": DIAGNOSTIC_CONTEXT_FINGERPRINT_VERSION,
        "description": complaint.description,
        "reported_error_code": complaint.reported_error_code,
        "reported_symptoms": canonical_symptoms(complaint.reported_symptoms),
        "priority": complaint.priority.value,
        "equipment_id": (
            str(complaint.equipment_id)
            if complaint.equipment_id is not None
            else None
        ),
        "equipment": (
            None
            if equipment is None
            else {
                "manufacturer": equipment.manufacturer,
                "model": equipment.model,
                "equipment_type": equipment.equipment_type,
            }
        ),
        "evidence_revision": evidence_revision,
        "service_history_digest": service_history_digest,
        "knowledge_corpus_digest": knowledge_corpus_digest,
    }


async def compute_diagnostic_context(
    session: AsyncSession,
    complaint: Complaint,
    equipment: Equipment | None,
    *,
    lock: bool = False,
) -> DiagnosticContext:
    """Compute the current readiness fingerprint and its evidence inputs."""

    evidence_revision = await compute_evidence_revision(session, complaint.id)
    service_payload = await _service_history_payload(
        session,
        complaint.equipment_id,
        lock=lock,
    )
    knowledge_payload = await _knowledge_corpus_payload(
        session,
        equipment,
        lock=lock,
    )
    service_history_digest = digest_records(service_payload)
    knowledge_corpus_digest = digest_records(knowledge_payload)
    payload = diagnostic_context_payload(
        complaint,
        equipment,
        evidence_revision=evidence_revision,
        service_history_digest=service_history_digest,
        knowledge_corpus_digest=knowledge_corpus_digest,
    )
    return DiagnosticContext(
        fingerprint=canonical_digest(payload),
        fingerprint_version=DIAGNOSTIC_CONTEXT_FINGERPRINT_VERSION,
        evidence_revision=evidence_revision,
        service_history_digest=service_history_digest,
        knowledge_corpus_digest=knowledge_corpus_digest,
    )


__all__ = [
    "DIAGNOSTIC_CONTEXT_FINGERPRINT_FIELDS",
    "DIAGNOSTIC_CONTEXT_FINGERPRINT_VERSION",
    "EVIDENCE_REVISION_EVENT_TYPES",
    "DiagnosticContext",
    "compute_diagnostic_context",
    "compute_evidence_revision",
    "diagnostic_context_payload",
]
