from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Complaint,
    CompletionReport,
    Conversation,
    Customer,
    Document,
    DocumentChunk,
    Equipment,
    Message,
    ServiceRecord,
    Technician,
    TechnicianAssignment,
    User,
    WorkOrder,
    WorkflowRun,
)
from app.models.enums import (
    AssignmentStatus,
    ComplaintChannel,
    ComplaintStatus,
    EvidenceStatus,
    MediaType,
    MessageSenderType,
    Priority,
    UserRole,
    WorkflowRunStatus,
    WorkOrderStatus,
)


async def add_user(
    session: AsyncSession,
    *,
    role: UserRole = UserRole.CUSTOMER,
    full_name: str = "Test User",
    email: str | None = None,
    phone: str | None = None,
) -> User:
    user = User(
        full_name=full_name,
        email=email or f"{uuid.uuid4().hex}@example.com",
        phone=phone,
        password_hash="not-a-real-hash",
        role=role,
    )
    session.add(user)
    await session.flush()
    return user


async def add_customer(
    session: AsyncSession,
) -> tuple[User, Customer]:
    user = await add_user(session, role=UserRole.CUSTOMER)
    customer = Customer(
        user=user,
        address="12 Test Street",
        preferred_language="en",
    )
    session.add(customer)
    await session.flush()
    return user, customer


async def add_technician(
    session: AsyncSession,
) -> tuple[User, Technician]:
    user = await add_user(session, role=UserRole.TECHNICIAN)
    technician = Technician(
        user=user,
        skills={
            "equipment_types": ["solar_inverter"],
            "experience_level": "intermediate",
        },
        service_area="Lahore",
    )
    session.add(technician)
    await session.flush()
    return user, technician


async def add_equipment(
    session: AsyncSession,
    customer: Customer,
    *,
    manufacturer: str = "Acme Solar",
    model: str = "INV-5000",
    serial_number: str | None = None,
) -> Equipment:
    equipment = Equipment(
        customer=customer,
        manufacturer=manufacturer,
        model=model,
        serial_number=serial_number or uuid.uuid4().hex[:12],
        equipment_type="solar_inverter",
    )
    session.add(equipment)
    await session.flush()
    return equipment


async def add_complaint(
    session: AsyncSession,
    customer: Customer,
    equipment: Equipment | None,
) -> Complaint:
    complaint = Complaint(
        customer=customer,
        equipment=equipment,
        description="The inverter stopped generating power this morning.",
        reported_symptoms=["no_generation", "red_warning_light"],
        reported_error_code="E-05",
        channel=ComplaintChannel.WEB,
    )
    session.add(complaint)
    await session.flush()
    return complaint


async def add_work_order(
    session: AsyncSession,
    complaint: Complaint,
    equipment: Equipment,
) -> WorkOrder:
    work_order = WorkOrder(
        complaint=complaint,
        equipment=equipment,
        title="Inspect inverter error E-05",
        description="Validate the reported error and inspect the inverter.",
        diagnostic_checklist=[
            {
                "task": "Verify the displayed error code",
                "source_document": "INV-5000-manual",
                "source_page": 42,
            }
        ],
    )
    session.add(work_order)
    await session.flush()
    return work_order


async def test_identity_profiles_are_created_and_linked(
    db_session: AsyncSession,
) -> None:
    customer_user, customer = await add_customer(db_session)
    technician_user, technician = await add_technician(db_session)

    assert customer.user is customer_user
    assert customer_user.customer is customer
    assert technician.user is technician_user
    assert technician_user.technician is technician

    assert customer_user.role is UserRole.CUSTOMER
    assert technician_user.role is UserRole.TECHNICIAN
    assert customer_user.is_active is True
    assert technician.is_available is True

    assert await db_session.scalar(select(func.count(User.id))) == 2
    assert await db_session.scalar(select(func.count(Customer.id))) == 1
    assert await db_session.scalar(select(func.count(Technician.id))) == 1


async def test_equipment_complaints_and_messages_are_linked(
    db_session: AsyncSession,
) -> None:
    _, customer = await add_customer(db_session)
    equipment = await add_equipment(db_session, customer)
    complaint = await add_complaint(db_session, customer, equipment)

    conversation = Conversation(
        complaint=complaint,
        channel=ComplaintChannel.WHATSAPP,
        external_conversation_id="wa-conversation-1",
    )
    message = Message(
        sender_type=MessageSenderType.CUSTOMER,
        content="Inverter showing error E-05.",
        external_message_id="wa-message-1",
    )
    reply = Message(
        sender_type=MessageSenderType.ASSISTANT,
        content="Please share the model number.",
        media_path="media/reply.txt",
        media_type=MediaType.DOCUMENT,
    )
    conversation.messages = [message, reply]
    db_session.add(conversation)
    await db_session.flush()

    assert equipment.customer is customer
    assert complaint.customer is customer
    assert complaint.equipment is equipment
    assert complaint.status is ComplaintStatus.RECEIVED
    assert complaint.priority is Priority.NORMAL
    assert complaint.description.startswith("The inverter")
    assert conversation.complaint is complaint
    assert conversation.messages == [message, reply]
    assert message.conversation is conversation


async def test_work_management_and_maintenance_records(
    db_session: AsyncSession,
) -> None:
    _, customer = await add_customer(db_session)
    _, technician = await add_technician(db_session)
    equipment = await add_equipment(db_session, customer)
    complaint = await add_complaint(db_session, customer, equipment)
    work_order = await add_work_order(db_session, complaint, equipment)

    assignment = TechnicianAssignment(
        work_order=work_order,
        technician=technician,
        assignment_status=AssignmentStatus.OFFERED,
    )
    service_record = ServiceRecord(
        equipment=equipment,
        work_order=work_order,
        technician=technician,
        findings="Error E-05 reproduced.",
        work_performed="Replaced the failed DC input connector.",
        parts_used=[{"part": "DC connector", "quantity": 1}],
    )
    completion_report = CompletionReport(
        work_order=work_order,
        summary="Inverter generation restored and verified.",
        evidence_status=EvidenceStatus.PENDING,
    )
    db_session.add_all([assignment, service_record, completion_report])
    await db_session.flush()

    assert work_order.complaint is complaint
    assert work_order.equipment is equipment
    assert work_order.status is WorkOrderStatus.DRAFT
    assert complaint.work_order is work_order
    assert assignment.work_order is work_order
    assert assignment.technician is technician
    assert service_record.equipment is equipment
    assert service_record.work_order is work_order
    assert service_record.technician is technician
    assert completion_report.work_order is work_order
    assert completion_report.evidence_status is EvidenceStatus.PENDING


async def test_documents_chunks_and_workflow_runs(
    db_session: AsyncSession,
) -> None:
    _, customer = await add_customer(db_session)
    equipment = await add_equipment(db_session, customer)
    complaint = await add_complaint(db_session, customer, equipment)

    document = Document(
        manufacturer="Acme Solar",
        model="INV-5000",
        document_name="INV-5000 Technical Manual",
        version="1.0",
        file_path="documents/acme/inv-5000-v1.pdf",
    )
    chunk = DocumentChunk(
        document=document,
        chunk_index=0,
        content="Error E-05 indicates a DC input fault.",
        page_number=42,
        chunk_metadata={"section": "troubleshooting"},
    )
    workflow_run = WorkflowRun(
        complaint=complaint,
        status=WorkflowRunStatus.RUNNING,
        current_step="diagnose",
    )
    db_session.add_all([document, chunk, workflow_run])
    await db_session.flush()

    assert chunk.document is document
    assert document.chunks == [chunk]
    assert workflow_run.complaint is complaint
    assert workflow_run.status is WorkflowRunStatus.RUNNING
    assert workflow_run.finished_at is None
    assert "embedding" not in DocumentChunk.__table__.c


async def test_duplicate_equipment_serial_is_rejected(
    db_session: AsyncSession,
) -> None:
    _, customer = await add_customer(db_session)
    await add_equipment(
        db_session,
        customer,
        manufacturer="Acme Solar",
        serial_number="SERIAL-001",
    )

    duplicate = Equipment(
        customer=customer,
        manufacturer="Acme Solar",
        model="INV-3000",
        serial_number="SERIAL-001",
        equipment_type="solar_inverter",
    )
    db_session.add(duplicate)

    with pytest.raises(IntegrityError):
        await db_session.flush()

    await db_session.rollback()


async def test_null_equipment_serials_are_allowed(
    db_session: AsyncSession,
) -> None:
    _, customer = await add_customer(db_session)
    first = Equipment(
        customer=customer,
        manufacturer="Acme Solar",
        model="INV-5000",
        serial_number=None,
        equipment_type="solar_inverter",
    )
    second = Equipment(
        customer=customer,
        manufacturer="Acme Solar",
        model="INV-3000",
        serial_number=None,
        equipment_type="solar_inverter",
    )
    db_session.add_all([first, second])
    await db_session.flush()

    assert first.id != second.id


async def test_invalid_foreign_key_is_rejected(
    db_session: AsyncSession,
) -> None:
    complaint = Complaint(
        customer_id=uuid.uuid4(),
        equipment_id=None,
        description="Orphan complaint",
        channel=ComplaintChannel.WEB,
    )
    db_session.add(complaint)

    with pytest.raises(IntegrityError):
        await db_session.flush()

    await db_session.rollback()


async def test_duplicate_unique_values_are_rejected(
    db_session: AsyncSession,
) -> None:
    email = f"{uuid.uuid4().hex}@example.com"
    await add_user(db_session, email=email)
    duplicate = User(
        full_name="Duplicate User",
        email=email,
        password_hash="not-a-real-hash",
        role=UserRole.CUSTOMER,
    )
    db_session.add(duplicate)

    with pytest.raises(IntegrityError):
        await db_session.flush()

    await db_session.rollback()


async def test_invalid_role_is_rejected_by_database(
    db_session: AsyncSession,
) -> None:
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                "INSERT INTO users "
                "(full_name, password_hash, role) "
                "VALUES (:full_name, :password_hash, :role)"
            ),
            {
                "full_name": "Invalid Role",
                "password_hash": "not-a-real-hash",
                "role": "superuser",
            },
        )

    await db_session.rollback()


async def test_invalid_status_is_rejected_by_database(
    db_session: AsyncSession,
) -> None:
    _, customer = await add_customer(db_session)

    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                "INSERT INTO complaints "
                "(customer_id, description, channel, status) "
                "VALUES (:customer_id, :description, :channel, :status)"
            ),
            {
                "customer_id": customer.id,
                "description": "Invalid status complaint",
                "channel": "web",
                "status": "not_a_real_status",
            },
        )

    await db_session.rollback()


async def test_complaint_equipment_must_belong_to_customer(
    db_session: AsyncSession,
) -> None:
    _, customer_a = await add_customer(db_session)
    _, customer_b = await add_customer(db_session)
    equipment_b = await add_equipment(db_session, customer_b)

    complaint = Complaint(
        customer=customer_a,
        equipment=equipment_b,
        description="Equipment from the wrong customer.",
        channel=ComplaintChannel.WEB,
    )
    db_session.add(complaint)

    with pytest.raises(IntegrityError):
        await db_session.flush()

    await db_session.rollback()


async def test_work_order_equipment_must_match_complaint(
    db_session: AsyncSession,
) -> None:
    _, customer = await add_customer(db_session)
    equipment_a = await add_equipment(db_session, customer)
    equipment_b = await add_equipment(db_session, customer)
    complaint = await add_complaint(db_session, customer, equipment_a)

    work_order = WorkOrder(
        complaint=complaint,
        equipment=equipment_b,
        title="Wrong equipment",
        description="Equipment does not match the complaint.",
    )
    db_session.add(work_order)

    with pytest.raises(IntegrityError):
        await db_session.flush()

    await db_session.rollback()


async def test_duplicate_external_message_ids_are_rejected(
    db_session: AsyncSession,
) -> None:
    _, customer = await add_customer(db_session)
    equipment = await add_equipment(db_session, customer)
    complaint = await add_complaint(db_session, customer, equipment)
    conversation = Conversation(
        complaint=complaint,
        channel=ComplaintChannel.WHATSAPP,
        external_conversation_id="wa-conversation-duplicate-test",
    )
    db_session.add(conversation)
    await db_session.flush()

    external_id = "wa-message-duplicate"
    first = Message(
        conversation=conversation,
        sender_type=MessageSenderType.CUSTOMER,
        content="First delivery",
        external_message_id=external_id,
    )
    db_session.add(first)
    await db_session.flush()

    duplicate = Message(
        conversation=conversation,
        sender_type=MessageSenderType.CUSTOMER,
        content="Duplicate delivery",
        external_message_id=external_id,
    )
    db_session.add(duplicate)

    with pytest.raises(IntegrityError):
        await db_session.flush()

    await db_session.rollback()


@pytest.mark.parametrize("preload_complaints", [False, True])
async def test_equipment_deletion_with_complaint_is_rejected(
    committed_db_session: AsyncSession,
    preload_complaints: bool,
) -> None:
    _, customer = await add_customer(committed_db_session)
    equipment = await add_equipment(committed_db_session, customer)
    complaint = await add_complaint(
        committed_db_session,
        customer,
        equipment,
    )
    await committed_db_session.commit()

    equipment_id = equipment.id
    complaint_id = complaint.id

    if preload_complaints:
        result = await committed_db_session.scalars(
            select(Equipment)
            .options(selectinload(Equipment.complaints))
            .where(Equipment.id == equipment_id)
        )
        target = result.one()
        assert len(target.complaints) == 1
    else:
        target = await committed_db_session.get(Equipment, equipment_id)
        assert target is not None

    await committed_db_session.delete(target)

    with pytest.raises(IntegrityError):
        await committed_db_session.commit()

    await committed_db_session.rollback()

    assert (
        await committed_db_session.get(Equipment, equipment_id)
        is not None
    )
    remaining = await committed_db_session.get(Complaint, complaint_id)
    assert remaining is not None
    assert remaining.equipment_id == equipment_id


async def test_service_record_equipment_must_match_work_order(
    db_session: AsyncSession,
) -> None:
    _, customer = await add_customer(db_session)
    _, technician = await add_technician(db_session)
    equipment_a = await add_equipment(db_session, customer)
    equipment_b = await add_equipment(db_session, customer)
    complaint = await add_complaint(db_session, customer, equipment_a)
    work_order = await add_work_order(
        db_session,
        complaint,
        equipment_a,
    )

    service_record = ServiceRecord(
        equipment=equipment_b,
        work_order=work_order,
        technician=technician,
    )
    db_session.add(service_record)

    with pytest.raises(IntegrityError):
        await db_session.flush()

    await db_session.rollback()


@pytest.mark.parametrize("version", [None, "1.0"])
async def test_duplicate_document_versions_are_rejected(
    db_session: AsyncSession,
    version: str | None,
) -> None:
    first = Document(
        manufacturer="Acme Solar",
        model="INV-5000",
        document_name="INV-5000 Technical Manual",
        version=version,
        file_path="documents/acme/inv-5000.pdf",
    )
    db_session.add(first)
    await db_session.flush()

    duplicate = Document(
        manufacturer="Acme Solar",
        model="INV-5000",
        document_name="INV-5000 Technical Manual",
        version=version,
        file_path="documents/acme/inv-5000-copy.pdf",
    )
    db_session.add(duplicate)

    with pytest.raises(IntegrityError):
        await db_session.flush()

    await db_session.rollback()


async def test_different_document_versions_are_allowed(
    db_session: AsyncSession,
) -> None:
    documents = [
        Document(
            manufacturer="Acme Solar",
            model="INV-5000",
            document_name="INV-5000 Technical Manual",
            version=version,
            file_path=f"documents/acme/inv-5000-{version}.pdf",
        )
        for version in (None, "1.0", "2.0")
    ]
    db_session.add_all(documents)
    await db_session.flush()

    count = await db_session.scalar(
        select(func.count(Document.id)).where(
            Document.manufacturer == "Acme Solar",
            Document.model == "INV-5000",
            Document.document_name == "INV-5000 Technical Manual",
        )
    )
    assert count == 3


async def test_document_defaults_to_inactive_in_orm_and_database(
    db_session: AsyncSession,
) -> None:
    document = Document(
        manufacturer="Acme Solar",
        model="INV-5000",
        document_name="ORM Default Manual",
        file_path="documents/acme/orm-default.pdf",
    )
    db_session.add(document)
    await db_session.flush()

    assert document.is_active is False

    raw_result = await db_session.execute(
        text(
            "INSERT INTO documents "
            "(manufacturer, model, document_name, file_path) "
            "VALUES (:manufacturer, :model, :document_name, :file_path) "
            "RETURNING is_active"
        ),
        {
            "manufacturer": "Acme Solar",
            "model": "INV-5000",
            "document_name": "Database Default Manual",
            "file_path": "documents/acme/database-default.pdf",
        },
    )
    assert raw_result.scalar_one() is False


async def test_updated_at_changes_on_orm_update(
    committed_db_session: AsyncSession,
) -> None:
    _, customer = await add_customer(committed_db_session)
    equipment = await add_equipment(committed_db_session, customer)
    complaint = await add_complaint(
        committed_db_session,
        customer,
        equipment,
    )
    await committed_db_session.commit()
    await committed_db_session.refresh(complaint)

    before = complaint.updated_at
    await asyncio.sleep(0.01)

    complaint.description = "Updated through the SQLAlchemy ORM."
    await committed_db_session.commit()
    await committed_db_session.refresh(complaint)

    assert before is not None
    assert complaint.updated_at > before


async def test_document_deletion_cascades_chunks_via_orm(
    db_session: AsyncSession,
) -> None:
    document = Document(
        manufacturer="Acme Solar",
        model="INV-5000",
        document_name="Cascade Manual",
        version="1.0",
        file_path="documents/acme/cascade.pdf",
    )
    chunk = DocumentChunk(
        document=document,
        chunk_index=0,
        content="Cascade test chunk.",
    )
    db_session.add_all([document, chunk])
    await db_session.flush()

    document_id = document.id
    await db_session.delete(document)
    await db_session.flush()

    remaining = await db_session.scalar(
        select(func.count(DocumentChunk.id)).where(
            DocumentChunk.document_id == document_id
        )
    )
    assert remaining == 0


async def test_document_chunk_foreign_key_cascades_in_database(
    db_session: AsyncSession,
) -> None:
    document = Document(
        manufacturer="Acme Solar",
        model="INV-5000",
        document_name="Database Cascade Manual",
        version="1.0",
        file_path="documents/acme/database-cascade.pdf",
    )
    chunk = DocumentChunk(
        document=document,
        chunk_index=0,
        content="Database cascade test chunk.",
    )
    db_session.add_all([document, chunk])
    await db_session.flush()

    document_id = document.id
    await db_session.execute(
        text("DELETE FROM documents WHERE id = :document_id"),
        {"document_id": document_id},
    )

    remaining = await db_session.scalar(
        select(func.count(DocumentChunk.id)).where(
            DocumentChunk.document_id == document_id
        )
    )
    assert remaining == 0


async def test_duplicate_clerk_user_ids_are_rejected(
    db_session: AsyncSession,
) -> None:
    clerk_user_id = f"user_{uuid.uuid4().hex}"
    first = User(
        full_name="First Clerk User",
        clerk_user_id=clerk_user_id,
        password_hash=None,
        role=UserRole.CUSTOMER,
    )
    db_session.add(first)
    await db_session.flush()

    duplicate = User(
        full_name="Duplicate Clerk User",
        clerk_user_id=clerk_user_id,
        password_hash=None,
        role=UserRole.CUSTOMER,
    )
    db_session.add(duplicate)

    with pytest.raises(IntegrityError):
        await db_session.flush()

    await db_session.rollback()


async def test_clerk_users_may_have_no_password_hash(
    db_session: AsyncSession,
) -> None:
    user = User(
        full_name="Clerk Only User",
        email=f"{uuid.uuid4().hex}@example.com",
        clerk_user_id=f"user_{uuid.uuid4().hex}",
        password_hash=None,
        role=UserRole.CUSTOMER,
    )
    db_session.add(user)
    await db_session.flush()

    assert user.password_hash is None
    assert user.clerk_user_id is not None
