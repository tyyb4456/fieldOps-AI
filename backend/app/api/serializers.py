from __future__ import annotations

from app.models.complaint import Complaint
from app.models.complaint_history import ComplaintHistory
from app.models.customer import Customer
from app.models.equipment import Equipment
from app.models.service_record import ServiceRecord
from app.models.technician import Technician
from app.models.technician_assignment import TechnicianAssignment
from app.models.user import User
from app.models.work_order import WorkOrder
from app.schemas.assignment import (
    AssignmentResponse,
    TechnicianSummaryResponse,
)
from app.schemas.complaint import (
    ComplaintHistoryResponse,
    ComplaintResponse,
)
from app.schemas.customer import CustomerProfileResponse
from app.schemas.equipment import EquipmentResponse
from app.schemas.service_record import ServiceRecordResponse
from app.schemas.user import UserMeResponse
from app.schemas.work_order import WorkOrderResponse


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
