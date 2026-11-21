from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.complaint import Complaint
from app.models.conversation import Conversation
from app.models.customer import Customer
from app.models.enums import (
    ComplaintChannel,
    ComplaintStatus,
    MessageSenderType,
    Priority,
    UserRole,
    WorkflowRunStatus,
    WorkflowRunType,
)
from app.models.equipment import Equipment
from app.models.message import Message
from app.models.technician import Technician
from app.models.user import User
from app.models.workflow_run import WorkflowRun
from app.services.complaints import lifecycle_service
from app.services.complaints.lifecycle import LifecycleActor, ReadinessMarker
from app.services.diagnostics.readiness_context import (
    DIAGNOSTIC_CONTEXT_FINGERPRINT_FIELDS,
    DIAGNOSTIC_CONTEXT_FINGERPRINT_VERSION,
    compute_diagnostic_context,
)
from tests.conftest import make_clerk_token

_UNSET = object()


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _token_for(subject: str) -> str:
    return make_clerk_token(sub=subject)


async def seed_customer(
    session: AsyncSession,
    *,
    full_name: str = "Test Customer",
    address: str | None = "12 Test Street",
    preferred_language: str | None = "en",
    is_active: bool = True,
) -> tuple[User, Customer, str]:
    subject = f"user_{uuid.uuid4().hex}"
    user = User(
        full_name=full_name,
        email=f"{uuid.uuid4().hex}@example.com",
        clerk_user_id=subject,
        password_hash=None,
        role=UserRole.CUSTOMER,
        is_active=is_active,
    )
    customer = Customer(
        user=user,
        address=address,
        preferred_language=preferred_language,
    )
    session.add(user)
    await session.commit()
    return user, customer, _token_for(subject)


async def seed_technician(
    session: AsyncSession,
    *,
    full_name: str = "Test Technician",
    is_active: bool = True,
) -> tuple[User, Technician, str]:
    subject = f"user_{uuid.uuid4().hex}"
    user = User(
        full_name=full_name,
        email=f"{uuid.uuid4().hex}@example.com",
        clerk_user_id=subject,
        password_hash=None,
        role=UserRole.TECHNICIAN,
        is_active=is_active,
    )
    technician = Technician(user=user)
    session.add(user)
    await session.commit()
    return user, technician, _token_for(subject)


async def seed_admin(
    session: AsyncSession,
    *,
    full_name: str = "Test Admin",
    is_active: bool = True,
) -> tuple[User, str]:
    subject = f"user_{uuid.uuid4().hex}"
    user = User(
        full_name=full_name,
        email=f"{uuid.uuid4().hex}@example.com",
        clerk_user_id=subject,
        password_hash=None,
        role=UserRole.ADMIN,
        is_active=is_active,
    )
    session.add(user)
    await session.commit()
    return user, _token_for(subject)


async def seed_conversation(
    session: AsyncSession,
    complaint: Complaint,
    *,
    channel: ComplaintChannel | None = None,
    external_conversation_id: str | None = None,
) -> Conversation:
    conversation = Conversation(
        complaint_id=complaint.id,
        channel=channel or complaint.channel,
        external_conversation_id=external_conversation_id,
    )
    session.add(conversation)
    await session.commit()
    return conversation


async def seed_message(
    session: AsyncSession,
    conversation: Conversation,
    *,
    sender_type: MessageSenderType = MessageSenderType.CUSTOMER,
    content: str = "Seeded message.",
    client_message_id: str | None = None,
    created_at: object | None = None,
) -> Message:
    values: dict[str, object] = {
        "conversation_id": conversation.id,
        "sender_type": sender_type,
        "content": content,
        "client_message_id": client_message_id,
    }
    if created_at is not None:
        values["created_at"] = created_at
    message = Message(**values)
    session.add(message)
    await session.commit()
    return message


async def seed_equipment(
    session: AsyncSession,
    customer: Customer,
    *,
    manufacturer: str = "Acme Solar",
    model: str = "INV-5000",
    serial_number: str | None | object = _UNSET,
    equipment_type: str = "solar_inverter",
    installation_date: date | None = None,
) -> Equipment:
    resolved_serial = (
        uuid.uuid4().hex[:12]
        if serial_number is _UNSET
        else serial_number
    )
    equipment = Equipment(
        customer_id=customer.id,
        manufacturer=manufacturer,
        model=model,
        serial_number=resolved_serial,
        equipment_type=equipment_type,
        installation_date=installation_date,
    )
    session.add(equipment)
    await session.commit()
    return equipment


async def seed_complaint(
    session: AsyncSession,
    customer: Customer,
    *,
    equipment: Equipment | None = None,
    description: str = "The inverter stopped generating power.",
    status: ComplaintStatus = ComplaintStatus.RECEIVED,
    channel: ComplaintChannel = ComplaintChannel.WEB,
) -> Complaint:
    complaint = Complaint(
        customer_id=customer.id,
        equipment_id=equipment.id if equipment is not None else None,
        description=description,
        channel=channel,
        status=status,
        priority=Priority.NORMAL,
    )
    session.add(complaint)
    await session.commit()
    return complaint


async def seed_completed_diagnostic_run(
    session: AsyncSession,
    complaint: Complaint,
    equipment: Equipment,
    *,
    result_status: str = "diagnosed",
    requires_escalation: bool = False,
    lifecycle_phase: str = "pre_conversion",
    finished_at: datetime | None = None,
) -> WorkflowRun:
    """Create a completed pre-conversion run with a captured fingerprint."""

    context = await compute_diagnostic_context(session, complaint, equipment)
    run = WorkflowRun(
        complaint_id=complaint.id,
        workflow_type=WorkflowRunType.DIAGNOSTIC_INVESTIGATION,
        input_payload={
            "focus": None,
            "lifecycle_phase": lifecycle_phase,
            "context_fingerprint": context.fingerprint,
            "context_fingerprint_version": (
                DIAGNOSTIC_CONTEXT_FINGERPRINT_VERSION
            ),
            "context_fingerprint_fields": list(
                DIAGNOSTIC_CONTEXT_FINGERPRINT_FIELDS
            ),
            "evidence_revision": context.evidence_revision,
            "context_captured_at": datetime.now(UTC).isoformat(),
        },
        result_payload={
            "complaint_id": str(complaint.id),
            "status": result_status,
            "requires_escalation": requires_escalation,
        },
        status=WorkflowRunStatus.COMPLETED,
        current_step="completed",
        finished_at=finished_at or datetime.now(UTC),
    )
    session.add(run)
    await session.commit()
    return run


async def seed_ready_complaint(
    session: AsyncSession,
    customer: Customer,
    equipment: Equipment,
    *,
    admin: User | None = None,
    description: str = "The inverter stopped generating power.",
) -> tuple[Complaint, WorkflowRun]:
    """Drive a complaint to readiness through a real lifecycle transition."""

    resolved_admin = admin
    if resolved_admin is None:
        resolved_admin, _ = await seed_admin(session)

    complaint = await seed_complaint(
        session,
        customer,
        equipment=equipment,
        description=description,
        status=ComplaintStatus.ANALYZING,
    )
    run = await seed_completed_diagnostic_run(session, complaint, equipment)
    fingerprint = run.input_payload["context_fingerprint"]
    marker = ReadinessMarker(
        readiness_source="lifecycle_v1",
        diagnostic_workflow_run_id=str(run.id),
        diagnostic_context_fingerprint=fingerprint,
        diagnostic_context_fingerprint_version=(
            DIAGNOSTIC_CONTEXT_FINGERPRINT_VERSION
        ),
        diagnostic_evidence_revision=run.input_payload["evidence_revision"],
    )
    await lifecycle_service.transition_complaint(
        session,
        complaint_id=complaint.id,
        target_status=ComplaintStatus.READY_FOR_WORK_ORDER,
        actor=LifecycleActor.ADMIN,
        actor_id=resolved_admin.id,
        expected_status=ComplaintStatus.ANALYZING,
        fields={"reason": "Diagnostic supports readiness."},
        readiness_marker=marker,
    )
    await session.commit()
    await session.refresh(complaint)
    return complaint, run
