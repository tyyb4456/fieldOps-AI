from __future__ import annotations

from typing import Any

from app.models.work_order_proposal import WorkOrderProposal
from app.services.diagnostics.diagnostics import DiagnosticResult

DIAGNOSTIC_DISCLAIMER = (
    "This is an AI-generated diagnostic recommendation. It must be verified by "
    "a qualified technician and does not replace approved service procedures or "
    "on-site inspection."
)


def diagnostic_result_payload(result: DiagnosticResult) -> dict[str, Any]:
    """Convert a diagnostic result into a JSONB-safe payload."""

    return {
        "complaint_id": str(result.complaint_id),
        "status": result.status.value,
        "summary": result.summary,
        "probable_causes": [
            {
                "cause": cause.cause,
                "basis": cause.basis,
                "evidence_chunk_ids": [
                    str(chunk_id) for chunk_id in cause.evidence_chunk_ids
                ],
            }
            for cause in result.probable_causes
        ],
        "recommended_checks": [
            {
                "step": check.step,
                "safety_note": check.safety_note,
                "evidence_chunk_ids": [
                    str(chunk_id) for chunk_id in check.evidence_chunk_ids
                ],
            }
            for check in result.recommended_checks
        ],
        "missing_information": list(result.missing_information),
        "safety_warnings": list(result.safety_warnings),
        "conflicting_evidence_notes": list(result.conflicting_evidence_notes),
        "requires_escalation": result.requires_escalation,
        "escalation_reason": result.escalation_reason,
        "citations": [
            {
                "source_id": citation.source_id,
                "chunk_id": str(citation.chunk_id),
                "document_id": str(citation.document_id),
                "document_name": citation.document_name,
                "manufacturer": citation.manufacturer,
                "model": citation.model,
                "version": citation.version,
                "page_number": citation.page_number,
                "chunk_index": citation.chunk_index,
                "excerpt": citation.excerpt,
            }
            for citation in result.citations
        ],
        "warnings": list(result.warnings),
        "disclaimer": DIAGNOSTIC_DISCLAIMER,
    }


def proposal_result_payload(
    proposal: WorkOrderProposal,
) -> dict[str, Any]:
    return {
        "proposal_id": str(proposal.id),
        "status": proposal.status.value,
    }


__all__ = [
    "DIAGNOSTIC_DISCLAIMER",
    "diagnostic_result_payload",
    "proposal_result_payload",
]
