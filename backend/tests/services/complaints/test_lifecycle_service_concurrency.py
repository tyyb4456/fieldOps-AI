from __future__ import annotations

import asyncio
import uuid
from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.complaint import Complaint
from app.models.complaint_history import ComplaintHistory
from app.models.enums import (
    ComplaintStatus,
    Priority,
    WorkOrderProposalStatus,
    WorkOrderStatus,
)
from app.models.user import User
from app.models.work_order import WorkOrder
from app.models.work_order_proposal import WorkOrderProposal
from app.services.agents.work_order_preparation_agent import (
    complaint_context_fingerprint,
)
from app.services.complaints import lifecycle_service
from app.services.complaints.lifecycle import (
    ComplaintStatusConflictError,
    LifecycleActor,
)
from app.services.work_orders.work_order_proposals import (
    InvalidProposalStateError,
    WorkOrderProposalService,
)
from tests.support import (
    seed_admin,
    seed_complaint,
    seed_customer,
    seed_equipment,
    seed_ready_complaint,
)


def _session_factory(
    session: AsyncSession,
) -> async_sessionmaker[AsyncSession]:
    assert session.bind is not None
    return async_sessionmaker(
        bind=session.bind,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


async def _start_and_wait_for_block(
    task: asyncio.Task[Any],
    started: asyncio.Event,
    *,
    timeout: float = 10.0,
) -> None:
    await asyncio.wait_for(started.wait(), timeout=timeout)
    await asyncio.sleep(0.1)
    assert task.done() is False


def _proposal(
    complaint: Complaint,
    *,
    status: WorkOrderProposalStatus = (WorkOrderProposalStatus.PENDING_APPROVAL),
    **overrides: object,
) -> WorkOrderProposal:
    values: dict[str, object] = {
        "complaint_id": complaint.id,
        "status": status,
        "title": "Inspect inverter",
        "problem_description": "Inverter offline",
        "proposed_scope": "Diagnose and repair",
        "technical_findings": "No DC output",
        "priority": Priority.NORMAL,
        "diagnostic_status": "diagnosed",
        "diagnostic_summary": "Diagnosis complete",
    }
    values.update(overrides)
    return WorkOrderProposal(**values)


def _proposal_service() -> WorkOrderProposalService:
    return WorkOrderProposalService(
        diagnostic_service=cast(Any, None),
        chat_model_factory=lambda: cast(Any, object()),
        max_tool_calls=1,
        max_model_calls=1,
        technician_limit=1,
    )


async def _history_sequences(
    session: AsyncSession,
    complaint_id: uuid.UUID,
) -> list[int]:
    return list(
        (
            await session.scalars(
                select(ComplaintHistory.sequence_number)
                .where(ComplaintHistory.complaint_id == complaint_id)
                .order_by(ComplaintHistory.sequence_number)
            )
        ).all()
    )


async def test_postgres_concurrent_transitions_serialize_and_append_history(
    committed_db_session: AsyncSession,
) -> None:
    _, customer, _ = await seed_customer(committed_db_session)
    equipment = await seed_equipment(committed_db_session, customer)
    complaint = await seed_complaint(
        committed_db_session,
        customer,
        equipment=equipment,
        status=ComplaintStatus.RECEIVED,
    )
    complaint_id = complaint.id
    admin, _ = await seed_admin(committed_db_session)
    factory = _session_factory(committed_db_session)

    async with factory() as winner:
        locked = await lifecycle_service.lock_complaint(winner, complaint_id)
        first = await lifecycle_service.transition_locked_complaint(
            winner,
            complaint=locked,
            target_status=ComplaintStatus.ANALYZING,
            actor=LifecycleActor.ADMIN,
            actor_id=admin.id,
            expected_status=ComplaintStatus.RECEIVED,
        )
        assert first.history.sequence_number == 1

        started = asyncio.Event()

        async def transition_after_winner() -> Any:
            async with factory() as loser:
                try:
                    started.set()
                    result = await lifecycle_service.transition_complaint(
                        loser,
                        complaint_id=complaint_id,
                        target_status=ComplaintStatus.AWAITING_CUSTOMER,
                        actor=LifecycleActor.ADMIN,
                        actor_id=admin.id,
                        expected_status=ComplaintStatus.ANALYZING,
                        fields={"reason": "Need a photo of the display"},
                    )
                    await loser.commit()
                    return result
                except Exception:
                    await loser.rollback()
                    raise

        task = asyncio.create_task(transition_after_winner())
        await _start_and_wait_for_block(task, started)
        assert task.done() is False

        await winner.commit()
        second = await asyncio.wait_for(task, timeout=10)

    assert second.history.sequence_number == 2

    async with factory() as probe:
        current = await probe.get(Complaint, complaint_id)
        assert current is not None
        assert current.status is ComplaintStatus.AWAITING_CUSTOMER
        assert await _history_sequences(probe, complaint_id) == [1, 2]


async def test_postgres_expected_status_conflict_under_concurrent_request(
    committed_db_session: AsyncSession,
) -> None:
    _, customer, _ = await seed_customer(committed_db_session)
    equipment = await seed_equipment(committed_db_session, customer)
    complaint = await seed_complaint(
        committed_db_session,
        customer,
        equipment=equipment,
        status=ComplaintStatus.RECEIVED,
    )
    complaint_id = complaint.id
    user, _, _ = await seed_customer(committed_db_session)
    admin, _ = await seed_admin(committed_db_session)
    factory = _session_factory(committed_db_session)

    async with factory() as winner:
        locked = await lifecycle_service.lock_complaint(winner, complaint_id)
        await lifecycle_service.transition_locked_complaint(
            winner,
            complaint=locked,
            target_status=ComplaintStatus.ANALYZING,
            actor=LifecycleActor.ADMIN,
            actor_id=admin.id,
            expected_status=ComplaintStatus.RECEIVED,
        )

        started = asyncio.Event()

        async def cancel_with_stale_expected_status() -> (
            ComplaintStatusConflictError | None
        ):
            async with factory() as loser:
                try:
                    started.set()
                    await lifecycle_service.cancel_complaint(
                        loser,
                        complaint_id=complaint_id,
                        actor=LifecycleActor.CUSTOMER,
                        actor_id=user.id,
                        expected_status=ComplaintStatus.RECEIVED,
                    )
                    await loser.commit()
                except ComplaintStatusConflictError as exc:
                    await loser.rollback()
                    return exc
            return None

        task = asyncio.create_task(cancel_with_stale_expected_status())
        await _start_and_wait_for_block(task, started)
        await winner.commit()
        error = await asyncio.wait_for(task, timeout=10)

    assert isinstance(error, ComplaintStatusConflictError)
    async with factory() as probe:
        current = await probe.get(Complaint, complaint_id)
        assert current is not None
        assert current.status is ComplaintStatus.ANALYZING
        assert await _history_sequences(probe, complaint_id) == [1]


async def test_postgres_concurrent_history_appends_use_unique_sequences(
    committed_db_session: AsyncSession,
) -> None:
    _, customer, _ = await seed_customer(committed_db_session)
    complaint = await seed_complaint(
        committed_db_session,
        customer,
        status=ComplaintStatus.RECEIVED,
    )
    complaint_id = complaint.id
    factory = _session_factory(committed_db_session)

    async def append(index: int) -> int:
        async with factory() as session:
            entry = await lifecycle_service.append_history(
                session,
                complaint_id=complaint_id,
                event_type="updated",
                from_status=ComplaintStatus.RECEIVED,
                to_status=ComplaintStatus.RECEIVED,
                changed_fields={"index": index},
                actor_id=None,
            )
            await session.commit()
            return entry.sequence_number

    sequences = await asyncio.gather(*(append(index) for index in range(6)))

    assert sorted(sequences) == [1, 2, 3, 4, 5, 6]
    async with factory() as probe:
        assert await _history_sequences(probe, complaint_id) == [
            1,
            2,
            3,
            4,
            5,
            6,
        ]
        count = await probe.scalar(
            select(func.count())
            .select_from(ComplaintHistory)
            .where(ComplaintHistory.complaint_id == complaint_id)
        )
        assert count == 6


async def test_postgres_concurrent_cancellation_supersedes_proposal_once(
    committed_db_session: AsyncSession,
) -> None:
    user, customer, _ = await seed_customer(committed_db_session)
    equipment = await seed_equipment(committed_db_session, customer)
    complaint = await seed_complaint(
        committed_db_session,
        customer,
        equipment=equipment,
        status=ComplaintStatus.READY_FOR_WORK_ORDER,
    )
    proposal = _proposal(complaint)
    committed_db_session.add(proposal)
    await committed_db_session.commit()
    complaint_id = complaint.id
    proposal_id = proposal.id
    factory = _session_factory(committed_db_session)

    async with factory() as winner:
        locked = await lifecycle_service.lock_complaint(winner, complaint_id)
        transition = await lifecycle_service.transition_locked_complaint(
            winner,
            complaint=locked,
            target_status=ComplaintStatus.CANCELLED,
            actor=LifecycleActor.CUSTOMER,
            actor_id=user.id,
            expected_status=ComplaintStatus.READY_FOR_WORK_ORDER,
        )
        assert transition.superseded_proposal_id == proposal_id

        started = asyncio.Event()

        async def cancel_after_winner() -> ComplaintStatusConflictError | None:
            async with factory() as loser:
                try:
                    started.set()
                    await lifecycle_service.cancel_complaint(
                        loser,
                        complaint_id=complaint_id,
                        actor=LifecycleActor.CUSTOMER,
                        actor_id=user.id,
                        expected_status=ComplaintStatus.READY_FOR_WORK_ORDER,
                    )
                    await loser.commit()
                except ComplaintStatusConflictError as exc:
                    await loser.rollback()
                    return exc
            return None

        task = asyncio.create_task(cancel_after_winner())
        await _start_and_wait_for_block(task, started)
        await winner.commit()
        error = await asyncio.wait_for(task, timeout=10)

    assert isinstance(error, ComplaintStatusConflictError)
    async with factory() as probe:
        current = await probe.get(Complaint, complaint_id)
        stored = await probe.get(WorkOrderProposal, proposal_id)
        assert current is not None
        assert stored is not None
        assert current.status is ComplaintStatus.CANCELLED
        assert stored.status is WorkOrderProposalStatus.SUPERSEDED
        assert stored.superseded_by_id == user.id
        assert stored.supersession_reason == "customer_cancelled"
        assert await _history_sequences(probe, complaint_id) == [1]


async def test_postgres_supersession_racing_approval_does_not_deadlock(
    committed_db_session: AsyncSession,
) -> None:
    _, customer, _ = await seed_customer(committed_db_session)
    equipment = await seed_equipment(committed_db_session, customer)
    admin, _ = await seed_admin(committed_db_session)
    complaint, _ = await seed_ready_complaint(
        committed_db_session,
        customer,
        equipment,
        admin=admin,
    )
    proposal = _proposal(
        complaint,
        context_snapshot={
            "context_fingerprint": complaint_context_fingerprint(
                complaint,
                equipment,
            )
        },
        created_by_id=admin.id,
    )
    committed_db_session.add(proposal)
    await committed_db_session.commit()
    complaint_id = complaint.id
    proposal_id = proposal.id
    admin_id = admin.id
    service = _proposal_service()
    factory = _session_factory(committed_db_session)

    async with factory() as winner:
        locked = await lifecycle_service.lock_complaint(winner, complaint_id)
        await lifecycle_service.transition_locked_complaint(
            winner,
            complaint=locked,
            target_status=ComplaintStatus.CANCELLED,
            actor=LifecycleActor.CUSTOMER,
            actor_id=customer.user_id,
            expected_status=ComplaintStatus.READY_FOR_WORK_ORDER,
        )

        started = asyncio.Event()

        async def approve_after_supersession() -> InvalidProposalStateError | None:
            async with factory() as loser:
                try:
                    started.set()
                    loser_admin = await loser.get(User, admin_id)
                    assert loser_admin is not None
                    await service.approve(
                        session=loser,
                        admin=loser_admin,
                        proposal_id=proposal_id,
                        technician_id=None,
                    )
                    await loser.commit()
                except InvalidProposalStateError as exc:
                    await loser.rollback()
                    return exc
            return None

        task = asyncio.create_task(approve_after_supersession())
        await _start_and_wait_for_block(task, started)
        await winner.commit()
        error = await asyncio.wait_for(task, timeout=10)

    assert isinstance(error, InvalidProposalStateError)
    async with factory() as probe:
        current = await probe.get(Complaint, complaint_id)
        stored = await probe.get(WorkOrderProposal, proposal_id)
        work_order_count = await probe.scalar(
            select(func.count())
            .select_from(WorkOrder)
            .where(WorkOrder.complaint_id == complaint_id)
        )
        assert current is not None
        assert stored is not None
        assert current.status is ComplaintStatus.CANCELLED
        assert stored.status is WorkOrderProposalStatus.SUPERSEDED
        assert work_order_count == 0


async def test_postgres_approval_racing_cancellation_creates_one_work_order(
    committed_db_session: AsyncSession,
) -> None:
    _, customer, _ = await seed_customer(committed_db_session)
    equipment = await seed_equipment(committed_db_session, customer)
    admin, _ = await seed_admin(committed_db_session)
    complaint, _ = await seed_ready_complaint(
        committed_db_session,
        customer,
        equipment,
        admin=admin,
    )
    proposal = _proposal(
        complaint,
        context_snapshot={
            "context_fingerprint": complaint_context_fingerprint(
                complaint,
                equipment,
            )
        },
        created_by_id=admin.id,
    )
    committed_db_session.add(proposal)
    await committed_db_session.commit()
    complaint_id = complaint.id
    proposal_id = proposal.id
    admin_id = admin.id
    service = _proposal_service()
    factory = _session_factory(committed_db_session)

    async with factory() as winner:
        winner_admin = await winner.get(User, admin_id)
        assert winner_admin is not None
        approved = await service.approve(
            session=winner,
            admin=winner_admin,
            proposal_id=proposal_id,
            technician_id=None,
        )
        assert approved.status is WorkOrderProposalStatus.APPROVED

        started = asyncio.Event()

        async def cancel_after_approval() -> ComplaintStatusConflictError | None:
            async with factory() as loser:
                try:
                    started.set()
                    await lifecycle_service.cancel_complaint(
                        loser,
                        complaint_id=complaint_id,
                        actor=LifecycleActor.CUSTOMER,
                        actor_id=customer.user_id,
                        expected_status=ComplaintStatus.READY_FOR_WORK_ORDER,
                    )
                    await loser.commit()
                except ComplaintStatusConflictError as exc:
                    await loser.rollback()
                    return exc
            return None

        task = asyncio.create_task(cancel_after_approval())
        await _start_and_wait_for_block(task, started)
        await winner.commit()
        error = await asyncio.wait_for(task, timeout=10)

    assert isinstance(error, ComplaintStatusConflictError)
    async with factory() as probe:
        current = await probe.get(Complaint, complaint_id)
        stored = await probe.get(WorkOrderProposal, proposal_id)
        work_orders = (
            await probe.scalars(
                select(WorkOrder).where(WorkOrder.complaint_id == complaint_id)
            )
        ).all()
        assert current is not None
        assert stored is not None
        assert current.status is ComplaintStatus.CONVERTED
        assert stored.status is WorkOrderProposalStatus.APPROVED
        assert len(work_orders) == 1
        assert work_orders[0].status is WorkOrderStatus.DRAFT


async def test_postgres_supersession_racing_rejection_does_not_deadlock(
    committed_db_session: AsyncSession,
) -> None:
    user, customer, _ = await seed_customer(committed_db_session)
    equipment = await seed_equipment(committed_db_session, customer)
    complaint = await seed_complaint(
        committed_db_session,
        customer,
        equipment=equipment,
        status=ComplaintStatus.READY_FOR_WORK_ORDER,
    )
    admin, _ = await seed_admin(committed_db_session)
    proposal = _proposal(complaint)
    committed_db_session.add(proposal)
    await committed_db_session.commit()
    complaint_id = complaint.id
    proposal_id = proposal.id
    admin_id = admin.id
    service = _proposal_service()
    factory = _session_factory(committed_db_session)

    async with factory() as winner:
        locked = await lifecycle_service.lock_complaint(winner, complaint_id)
        await lifecycle_service.transition_locked_complaint(
            winner,
            complaint=locked,
            target_status=ComplaintStatus.CANCELLED,
            actor=LifecycleActor.CUSTOMER,
            actor_id=user.id,
            expected_status=ComplaintStatus.READY_FOR_WORK_ORDER,
        )

        started = asyncio.Event()

        async def reject_after_supersession() -> InvalidProposalStateError | None:
            async with factory() as loser:
                try:
                    started.set()
                    loser_admin = await loser.get(User, admin_id)
                    assert loser_admin is not None
                    await service.reject(
                        session=loser,
                        admin=loser_admin,
                        proposal_id=proposal_id,
                        reason="Historical rejection attempt",
                    )
                    await loser.commit()
                except InvalidProposalStateError as exc:
                    await loser.rollback()
                    return exc
            return None

        task = asyncio.create_task(reject_after_supersession())
        await _start_and_wait_for_block(task, started)
        await winner.commit()
        error = await asyncio.wait_for(task, timeout=10)

    assert isinstance(error, InvalidProposalStateError)
    async with factory() as probe:
        stored = await probe.get(WorkOrderProposal, proposal_id)
        assert stored is not None
        assert stored.status is WorkOrderProposalStatus.SUPERSEDED
        assert stored.reviewed_by_id is None
        assert stored.rejection_reason is None


async def test_postgres_rejection_racing_cancellation_preserves_human_decision(
    committed_db_session: AsyncSession,
) -> None:
    user, customer, _ = await seed_customer(committed_db_session)
    equipment = await seed_equipment(committed_db_session, customer)
    complaint = await seed_complaint(
        committed_db_session,
        customer,
        equipment=equipment,
        status=ComplaintStatus.READY_FOR_WORK_ORDER,
    )
    admin, _ = await seed_admin(committed_db_session)
    proposal = _proposal(complaint)
    committed_db_session.add(proposal)
    await committed_db_session.commit()
    complaint_id = complaint.id
    proposal_id = proposal.id
    admin_id = admin.id
    service = _proposal_service()
    factory = _session_factory(committed_db_session)

    async with factory() as winner:
        winner_admin = await winner.get(User, admin_id)
        assert winner_admin is not None
        rejected = await service.reject(
            session=winner,
            admin=winner_admin,
            proposal_id=proposal_id,
            reason="Documented human rejection",
        )
        assert rejected.status is WorkOrderProposalStatus.REJECTED

        started = asyncio.Event()

        async def cancel_after_rejection() -> Any:
            async with factory() as loser:
                try:
                    started.set()
                    result = await lifecycle_service.cancel_complaint(
                        loser,
                        complaint_id=complaint_id,
                        actor=LifecycleActor.CUSTOMER,
                        actor_id=user.id,
                        expected_status=ComplaintStatus.READY_FOR_WORK_ORDER,
                    )
                    await loser.commit()
                    return result
                except Exception:
                    await loser.rollback()
                    raise

        task = asyncio.create_task(cancel_after_rejection())
        await _start_and_wait_for_block(task, started)
        await winner.commit()
        transition = await asyncio.wait_for(task, timeout=10)

    assert transition.superseded_proposal_id is None
    async with factory() as probe:
        current = await probe.get(Complaint, complaint_id)
        stored = await probe.get(WorkOrderProposal, proposal_id)
        assert current is not None
        assert stored is not None
        assert current.status is ComplaintStatus.CANCELLED
        assert stored.status is WorkOrderProposalStatus.REJECTED
        assert stored.reviewed_by_id == admin_id
        assert stored.rejection_reason == "Documented human rejection"
        assert stored.superseded_at is None
