from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.background_task import BackgroundTask
from app.models.enums import (
    BackgroundTaskStatus,
    WorkflowRunStatus,
    WorkflowRunType,
    WorkOrderProposalStatus,
)
from app.models.work_order_proposal import WorkOrderProposal
from app.models.workflow_run import WorkflowRun
from app.services.tasks.execution import (
    WORK_ORDER_PROPOSAL_TASK_NAME,
    create_background_task,
)
from app.services.tasks.recovery import (
    RECONCILED_RUNNING_TASK_ERROR,
    RECONCILED_RUNNING_WORKFLOW_ERROR,
    fail_stale_running_tasks,
)
from tests.services.work_orders.test_work_order_proposals import (
    _diagnosis,
    _seed_ready_complaint,
    _seed_skilled_technician,
    _service,
)
from tests.support import seed_admin

STALE_AGE = timedelta(hours=2)


async def _seed_proposal_case(
    session: AsyncSession,
    *,
    with_proposal: bool,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID | None]:
    """Seed a stale running proposal run, optionally with its proposal.

    The proposal is committed in a separate transaction, which models the
    boundary where the graph persisted the proposal but the worker stopped
    before the run and task were finalized.
    """

    admin, _ = await seed_admin(session)
    await _seed_skilled_technician(session)
    _, _, complaint = await _seed_ready_complaint(session)
    service = _service(_diagnosis(complaint.id))
    stale = datetime.now(UTC) - STALE_AGE

    run = WorkflowRun(
        complaint_id=complaint.id,
        workflow_type=WorkflowRunType.WORK_ORDER_PROPOSAL,
        requested_by_id=admin.id,
        status=WorkflowRunStatus.RUNNING,
        current_step="persisting_proposal",
    )
    session.add(run)
    await session.flush()
    task = create_background_task(
        task_name=WORK_ORDER_PROPOSAL_TASK_NAME,
        celery_task_id=str(uuid.uuid4()),
        resource_type="workflow_run",
        resource_id=run.id,
    )
    task.status = BackgroundTaskStatus.RUNNING
    task.started_at = stale
    task.attempts = 1
    task.created_at = stale
    session.add(task)
    await session.commit()

    proposal_id: uuid.UUID | None = None
    if with_proposal:
        diagnosis = _diagnosis(complaint.id)
        context = await service.validate_generation_context(
            session=session,
            user=admin,
            complaint_id=complaint.id,
            workflow_run_id=run.id,
        )
        preparation = await service.prepare_generation(
            session=session,
            context=context,
            diagnosis=diagnosis,
        )
        proposal = await service.persist_prepared_proposal(
            session=session,
            user=admin,
            context=context,
            diagnosis=diagnosis,
            preparation=preparation,
            workflow_run_id=run.id,
        )
        await session.commit()
        proposal_id = proposal.id

    return run.id, task.id, proposal_id


async def _count_proposals(session: AsyncSession) -> int:
    return int(
        await session.scalar(select(func.count(WorkOrderProposal.id))) or 0
    )


@pytest.mark.asyncio
async def test_recovery_reconciles_persisted_proposal_successfully(
    migrated_db_session: AsyncSession,
) -> None:
    run_id, task_id, proposal_id = await _seed_proposal_case(
        migrated_db_session,
        with_proposal=True,
    )
    assert proposal_id is not None

    reconciled = await fail_stale_running_tasks(
        migrated_db_session,
        stale_after_seconds=60,
    )

    assert reconciled == (task_id,)

    run = await migrated_db_session.get(
        WorkflowRun,
        run_id,
        populate_existing=True,
    )
    task = await migrated_db_session.get(
        BackgroundTask,
        task_id,
        populate_existing=True,
    )
    proposal = await migrated_db_session.get(
        WorkOrderProposal,
        proposal_id,
        populate_existing=True,
    )
    assert run is not None
    assert task is not None
    assert proposal is not None
    assert run.status is WorkflowRunStatus.COMPLETED
    assert run.current_step == "completed"
    assert run.finished_at is not None
    assert run.error_message is None
    assert run.result_payload == {
        "proposal_id": str(proposal_id),
        "status": "pending_approval",
    }
    assert task.status is BackgroundTaskStatus.SUCCEEDED
    assert task.finished_at is not None
    assert task.error_message is None
    assert proposal.status is WorkOrderProposalStatus.PENDING_APPROVAL
    assert proposal.source_workflow_run_id == run_id
    assert await _count_proposals(migrated_db_session) == 1


@pytest.mark.asyncio
async def test_repeated_recovery_is_idempotent_and_creates_no_duplicate(
    migrated_db_session: AsyncSession,
) -> None:
    run_id, task_id, proposal_id = await _seed_proposal_case(
        migrated_db_session,
        with_proposal=True,
    )
    assert proposal_id is not None

    first = await fail_stale_running_tasks(
        migrated_db_session,
        stale_after_seconds=60,
    )
    assert first == (task_id,)
    run = await migrated_db_session.get(
        WorkflowRun,
        run_id,
        populate_existing=True,
    )
    assert run is not None
    finished_at = run.finished_at
    result_payload = dict(run.result_payload or {})

    second = await fail_stale_running_tasks(
        migrated_db_session,
        stale_after_seconds=60,
    )
    third = await fail_stale_running_tasks(
        migrated_db_session,
        stale_after_seconds=60,
    )

    assert second == ()
    assert third == ()
    refreshed_run = await migrated_db_session.get(
        WorkflowRun,
        run_id,
        populate_existing=True,
    )
    refreshed_task = await migrated_db_session.get(
        BackgroundTask,
        task_id,
        populate_existing=True,
    )
    assert refreshed_run is not None
    assert refreshed_task is not None
    assert refreshed_run.status is WorkflowRunStatus.COMPLETED
    assert refreshed_run.finished_at == finished_at
    assert refreshed_run.result_payload == result_payload
    assert refreshed_task.status is BackgroundTaskStatus.SUCCEEDED
    assert await _count_proposals(migrated_db_session) == 1


@pytest.mark.asyncio
async def test_recovery_only_uses_proposal_owned_by_the_same_run(
    migrated_db_session: AsyncSession,
) -> None:
    failed_run_id, failed_task_id, failed_proposal_id = (
        await _seed_proposal_case(
            migrated_db_session,
            with_proposal=False,
        )
    )
    assert failed_proposal_id is None
    recovered_run_id, recovered_task_id, recovered_proposal_id = (
        await _seed_proposal_case(
            migrated_db_session,
            with_proposal=True,
        )
    )
    assert recovered_proposal_id is not None

    reconciled = await fail_stale_running_tasks(
        migrated_db_session,
        stale_after_seconds=60,
    )

    assert set(reconciled) == {failed_task_id, recovered_task_id}

    failed_run = await migrated_db_session.get(
        WorkflowRun,
        failed_run_id,
        populate_existing=True,
    )
    failed_task = await migrated_db_session.get(
        BackgroundTask,
        failed_task_id,
        populate_existing=True,
    )
    assert failed_run is not None
    assert failed_task is not None
    assert failed_run.status is WorkflowRunStatus.FAILED
    assert failed_run.current_step == "failed"
    assert failed_run.error_message == RECONCILED_RUNNING_WORKFLOW_ERROR
    assert failed_task.status is BackgroundTaskStatus.FAILED
    assert failed_task.error_message == RECONCILED_RUNNING_TASK_ERROR

    recovered_run = await migrated_db_session.get(
        WorkflowRun,
        recovered_run_id,
        populate_existing=True,
    )
    recovered_task = await migrated_db_session.get(
        BackgroundTask,
        recovered_task_id,
        populate_existing=True,
    )
    recovered_proposal = await migrated_db_session.get(
        WorkOrderProposal,
        recovered_proposal_id,
        populate_existing=True,
    )
    assert recovered_run is not None
    assert recovered_task is not None
    assert recovered_proposal is not None
    assert recovered_run.status is WorkflowRunStatus.COMPLETED
    assert recovered_run.result_payload == {
        "proposal_id": str(recovered_proposal_id),
        "status": "pending_approval",
    }
    assert recovered_task.status is BackgroundTaskStatus.SUCCEEDED
    assert recovered_proposal.source_workflow_run_id == recovered_run_id

    proposals = (
        await migrated_db_session.execute(
            select(WorkOrderProposal).order_by(
                WorkOrderProposal.created_at.asc()
            )
        )
    ).scalars().all()
    assert len(proposals) == 1
    assert proposals[0].id == recovered_proposal_id
