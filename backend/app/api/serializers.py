from __future__ import annotations

import uuid

from app.models.complaint import Complaint
from app.models.complaint_history import ComplaintHistory
from app.models.completion_report import CompletionReport
from app.models.customer import Customer
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.enums import WorkflowRunType
from app.models.equipment import Equipment
from app.models.service_record import ServiceRecord
from app.models.technician import Technician
from app.models.technician_assignment import TechnicianAssignment
from app.models.user import User
from app.models.work_order import WorkOrder
from app.models.work_order_proposal import WorkOrderProposal
from app.models.workflow_run import WorkflowRun
from app.schemas.accounts.user import UserMeResponse
from app.schemas.assignments.assignment import (
    AssignmentResponse,
    TechnicianSummaryResponse,
)
from app.schemas.complaints.complaint import (
    ComplaintHistoryResponse,
    ComplaintResponse,
)
from app.schemas.customers.customer import CustomerProfileResponse
from app.schemas.diagnostics.diagnostic import (
    DiagnosticInvestigationResponse,
    DiagnosticStatus,
)
from app.schemas.documents.document import (
    DocumentChunkResponse,
    DocumentResponse,
)
from app.schemas.equipment.equipment import EquipmentResponse
from app.schemas.rag.knowledge_answer import CitationResponse
from app.schemas.work_orders.completion_report import CompletionReportResponse
from app.schemas.work_orders.service_record import ServiceRecordResponse
from app.schemas.work_orders.work_order import WorkOrderResponse
from app.schemas.work_orders.work_order_proposal import (
    TechnicianRecommendationResponse,
    WorkOrderProposalResponse,
)
from app.schemas.workflow_runs.workflow_run import (
    WorkflowRunAcceptedResponse,
    WorkflowRunDetailResponse,
    WorkflowRunResponse,
)


def user_me_response(user: User) -> UserMeResponse:
    return UserMeResponse(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        phone=user.phone,
        role=user.role,
        is_active=user.is_active,
        customer_id=(
            user.customer.id if user.customer is not None else None
        ),
        technician_id=(
            user.technician.id if user.technician is not None else None
        ),
    )


def customer_profile_response(
    customer: Customer,
    user: User | None = None,
) -> CustomerProfileResponse:
    owner = user if user is not None else customer.user
    return CustomerProfileResponse(
        id=customer.id,
        full_name=owner.full_name,
        email=owner.email,
        phone=owner.phone,
        address=customer.address,
        preferred_language=customer.preferred_language,
        is_active=owner.is_active,
        created_at=customer.created_at,
    )


def equipment_response(equipment: Equipment) -> EquipmentResponse:
    return EquipmentResponse(
        id=equipment.id,
        customer_id=equipment.customer_id,
        manufacturer=equipment.manufacturer,
        model=equipment.model,
        serial_number=equipment.serial_number,
        equipment_type=equipment.equipment_type,
        installation_date=equipment.installation_date,
        created_at=equipment.created_at,
    )


def complaint_response(complaint: Complaint) -> ComplaintResponse:
    return ComplaintResponse(
        id=complaint.id,
        customer_id=complaint.customer_id,
        equipment_id=complaint.equipment_id,
        description=complaint.description,
        reported_symptoms=complaint.reported_symptoms,
        reported_error_code=complaint.reported_error_code,
        channel=complaint.channel,
        status=complaint.status,
        priority=complaint.priority,
        created_at=complaint.created_at,
        updated_at=complaint.updated_at,
    )


def complaint_history_response(
    history: ComplaintHistory,
) -> ComplaintHistoryResponse:
    return ComplaintHistoryResponse(
        id=history.id,
        complaint_id=history.complaint_id,
        sequence_number=history.sequence_number,
        event_type=history.event_type,
        from_status=history.from_status,
        to_status=history.to_status,
        changed_fields=history.changed_fields,
        actor_id=history.actor_id,
        created_at=history.created_at,
    )


def work_order_response(work_order: WorkOrder) -> WorkOrderResponse:
    return WorkOrderResponse(
        id=work_order.id,
        complaint_id=work_order.complaint_id,
        equipment_id=work_order.equipment_id,
        title=work_order.title,
        description=work_order.description,
        diagnostic_checklist=work_order.diagnostic_checklist,
        priority=work_order.priority,
        status=work_order.status,
        created_at=work_order.created_at,
        updated_at=work_order.updated_at,
    )


def assignment_response(
    assignment: TechnicianAssignment,
) -> AssignmentResponse:
    return AssignmentResponse(
        id=assignment.id,
        work_order_id=assignment.work_order_id,
        technician_id=assignment.technician_id,
        assignment_status=assignment.assignment_status,
        assigned_at=assignment.assigned_at,
        accepted_at=assignment.accepted_at,
        rejected_at=assignment.rejected_at,
    )


def technician_summary_response(
    technician: Technician,
) -> TechnicianSummaryResponse:
    return TechnicianSummaryResponse(
        id=technician.id,
        user_id=technician.user_id,
        full_name=technician.user.full_name,
        email=technician.user.email,
        skills=technician.skills,
        service_area=technician.service_area,
        is_available=technician.is_available,
    )


def service_record_response(
    service_record: ServiceRecord,
) -> ServiceRecordResponse:
    return ServiceRecordResponse(
        id=service_record.id,
        equipment_id=service_record.equipment_id,
        work_order_id=service_record.work_order_id,
        technician_id=service_record.technician_id,
        findings=service_record.findings,
        work_performed=service_record.work_performed,
        parts_used=service_record.parts_used,
        recorded_at=service_record.recorded_at,
    )


def completion_report_response(
    completion_report: CompletionReport,
) -> CompletionReportResponse:
    return CompletionReportResponse(
        id=completion_report.id,
        work_order_id=completion_report.work_order_id,
        service_record_id=completion_report.service_record_id,
        summary=completion_report.summary,
        evidence_status=completion_report.evidence_status,
        verification_notes=completion_report.verification_notes,
        submitted_at=completion_report.submitted_at,
        verified_at=completion_report.verified_at,
    )


def document_response(document: Document) -> DocumentResponse:
    return DocumentResponse(
        id=document.id,
        manufacturer=document.manufacturer,
        model=document.model,
        document_name=document.document_name,
        version=document.version,
        original_filename=document.original_filename,
        content_type=document.content_type,
        byte_size=document.byte_size,
        checksum_sha256=document.checksum_sha256,
        uploaded_by_id=document.uploaded_by_id,
        ingestion_status=document.ingestion_status,
        ingestion_error=document.ingestion_error,
        ingested_at=document.ingested_at,
        is_active=document.is_active,
        created_at=document.created_at,
    )


def document_chunk_response(
    chunk: DocumentChunk,
) -> DocumentChunkResponse:
    return DocumentChunkResponse(
        id=chunk.id,
        document_id=chunk.document_id,
        chunk_index=chunk.chunk_index,
        content=chunk.content,
        page_number=chunk.page_number,
        metadata=chunk.chunk_metadata,
    )


def workflow_run_response(
    workflow_run: WorkflowRun,
) -> WorkflowRunResponse:
    return WorkflowRunResponse(
        id=workflow_run.id,
        complaint_id=workflow_run.complaint_id,
        workflow_type=workflow_run.workflow_type,
        status=workflow_run.status,
        current_step=workflow_run.current_step,
        started_at=workflow_run.started_at,
        finished_at=workflow_run.finished_at,
        error_message=workflow_run.error_message,
    )


def workflow_run_accepted_response(
    workflow_run: WorkflowRun,
) -> WorkflowRunAcceptedResponse:
    if workflow_run.workflow_type is None:
        raise ValueError("Accepted workflow runs require a workflow type")
    return WorkflowRunAcceptedResponse(
        workflow_run_id=workflow_run.id,
        complaint_id=workflow_run.complaint_id,
        workflow_type=workflow_run.workflow_type,
        status=workflow_run.status,
        current_step=workflow_run.current_step,
    )


def workflow_run_detail_response(
    workflow_run: WorkflowRun,
) -> WorkflowRunDetailResponse:
    diagnostic = None
    proposal_id = None
    payload = workflow_run.result_payload
    if isinstance(payload, dict):
        if (
            workflow_run.workflow_type
            is WorkflowRunType.DIAGNOSTIC_INVESTIGATION
        ):
            diagnostic = DiagnosticInvestigationResponse.model_validate(
                payload
            )
        raw_proposal_id = payload.get("proposal_id")
        if raw_proposal_id is not None:
            proposal_id = uuid.UUID(str(raw_proposal_id))
    return WorkflowRunDetailResponse(
        id=workflow_run.id,
        complaint_id=workflow_run.complaint_id,
        workflow_type=workflow_run.workflow_type,
        status=workflow_run.status,
        current_step=workflow_run.current_step,
        started_at=workflow_run.started_at,
        finished_at=workflow_run.finished_at,
        error_message=workflow_run.error_message,
        diagnostic=diagnostic,
        proposal_id=proposal_id,
    )


def work_order_proposal_response(
    proposal: WorkOrderProposal,
) -> WorkOrderProposalResponse:
    recommendations = [
        TechnicianRecommendationResponse.model_validate(item)
        for item in proposal.technician_recommendations
        if isinstance(item, dict)
    ]
    citations = [
        CitationResponse.model_validate(item)
        for item in proposal.citations
        if isinstance(item, dict)
    ]
    return WorkOrderProposalResponse(
        id=proposal.id,
        complaint_id=proposal.complaint_id,
        status=proposal.status,
        title=proposal.title,
        problem_description=proposal.problem_description,
        proposed_scope=proposal.proposed_scope,
        technical_findings=proposal.technical_findings,
        recommended_actions=[
            str(item) for item in proposal.recommended_actions
        ],
        required_skills=[str(item) for item in proposal.required_skills],
        required_parts=[str(item) for item in proposal.required_parts],
        priority=proposal.priority,
        estimated_duration_minutes=proposal.estimated_duration_minutes,
        safety_warnings=[str(item) for item in proposal.safety_warnings],
        missing_information=[
            str(item) for item in proposal.missing_information
        ],
        generation_warnings=[
            str(item) for item in proposal.generation_warnings
        ],
        diagnostic_status=DiagnosticStatus(proposal.diagnostic_status),
        diagnostic_summary=proposal.diagnostic_summary,
        diagnostic_snapshot=proposal.diagnostic_snapshot,
        citations=citations,
        requires_escalation=proposal.requires_escalation,
        escalation_reason=proposal.escalation_reason,
        technician_recommendations=recommendations,
        selected_technician_id=proposal.selected_technician_id,
        created_by_id=proposal.created_by_id,
        reviewed_by_id=proposal.reviewed_by_id,
        reviewed_at=proposal.reviewed_at,
        rejection_reason=proposal.rejection_reason,
        resulting_work_order_id=proposal.resulting_work_order_id,
        resulting_assignment_id=proposal.resulting_assignment_id,
        created_at=proposal.created_at,
        updated_at=proposal.updated_at,
    )
