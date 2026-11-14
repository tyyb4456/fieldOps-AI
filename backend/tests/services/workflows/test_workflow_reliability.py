from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.api.dependencies.diagnostics import get_diagnostic_service
from app.core.config import settings
from app.main import app
from app.models.background_task import BackgroundTask
from app.models.enums import (
    BackgroundTaskStatus,
    OutboxEventStatus,
    WorkflowRunStatus,
    WorkflowRunType,
)
from app.models.outbox_event import OutboxEvent
from app.models.work_order_proposal import WorkOrderProposal
from app.models.workflow_run import WorkflowRun
from app.services.tasks.execution import (
    DIAGNOSTIC_INVESTIGATION_TASK_NAME,
    WORK_ORDER_PROPOSAL_TASK_NAME,
    create_background_task,
)
from app.services.work_orders.work_order_proposals import (
    ProposalAlreadyPendingError,
    ProposalGenerationError,
)
from app.services.workflows import scheduling
from app.services.workflows.errors import (
    GENERIC_WORKFLOW_ERROR,
    WorkflowExecutionBusyError,
    WorkflowPermanentError,
)
from app.services.workflows.executor import execute_workflow
from app.services.workflows.scheduling import schedule_diagnostic_investigation
from app.tasks import workflows as workflow_tasks
from app.tasks.workflows import _execute_task, _finalize_failed_task, run_workflow
from tests.services.work_orders.test_work_order_proposals import (
    StubDiagnosticService,
    _diagnosis,
    _seed_ready_complaint,
    _seed_skilled_technician,
    _service,
)
from tests.support import (
    bearer,
    seed_admin,
    seed_complaint,
    seed_customer,
    seed_equipment,
)


def _session_factory(session: AsyncSession) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=cast(AsyncEngine, session.bind),
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


class _FakeVectorIndex:
    def __init__(self, **kwargs: object) -> None:
        pass

    async def close(self) -> None:
        return None


class _BlockingDiagnosticService(StubDiagnosticService):
    def __init__(
        self,
        result: Any,
        entered: asyncio.Event,
        release: asyncio.Event,
    ) -> None:
        super().__init__(result)
        self._entered = entered
        self._release = release
        self.executions = 0

    async def run_agent(self, **kwargs: Any) -> Any:
        self.executions += 1
        self._entered.set()
        await self._release.wait()
        return await super().run_agent(**kwargs)


async def _seed_run(
    session: AsyncSession,
    *,
    complaint_id: uuid.UUID,
    admin_id: uuid.UUID,
    workflow_type: WorkflowRunType = WorkflowRunType.DIAGNOSTIC_INVESTIGATION,
    run_status: WorkflowRunStatus = WorkflowRunStatus.RUNNING,
    task_status: BackgroundTaskStatus = BackgroundTaskStatus.PENDING,
    error_message: str | None = None,
) -> tuple[WorkflowRun, BackgroundTask]:
    run = WorkflowRun(
        complaint_id=complaint_id,
        workflow_type=workflow_type,
        requested_by_id=admin_id,
        status=run_status,
        current_step="queued",
        error_message=error_message,
    )
    session.add(run)
    await session.flush()
    task = create_background_task(
        task_name=(
            DIAGNOSTIC_INVESTIGATION_TASK_NAME
            if workflow_type is WorkflowRunType.DIAGNOSTIC_INVESTIGATION
            else WORK_ORDER_PROPOSAL_TASK_NAME
        ),
        celery_task_id=str(uuid.uuid4()),
        resource_type="workflow_run",
        resource_id=run.id,
    )
    task.status = task_status
    session.add(task)
    await session.commit()
    return run, task


async def _seed_complaint_case(session: AsyncSession):
    _, customer, _ = await seed_customer(session)
    equipment = await seed_equipment(session, customer)
    return await seed_complaint(session, customer, equipment=equipment)


@pytest.mark.asyncio
async def test_duplicate_delivery_marks_failed_run_task_failed(
    migrated_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin, _ = await seed_admin(migrated_db_session)
    complaint = await _seed_complaint_case(migrated_db_session)
    run, task = await _seed_run(
        migrated_db_session,
        complaint_id=complaint.id,
        admin_id=admin.id,
        run_status=WorkflowRunStatus.FAILED,
        task_status=BackgroundTaskStatus.RUNNING,
        error_message="The diagnostic agent is unavailable.",
    )
    monkeypatch.setattr(
        workflow_tasks,
        "async_session_factory",
        _session_factory(migrated_db_session),
    )

    result = await run_workflow(run.id, task.id)

    assert result == str(run.id)
    await migrated_db_session.rollback()
    await migrated_db_session.refresh(task)
    await migrated_db_session.refresh(run)
    assert task.status is BackgroundTaskStatus.FAILED
    assert task.error_message == "The diagnostic agent is unavailable."
    assert run.status is WorkflowRunStatus.FAILED


@pytest.mark.asyncio
async def test_duplicate_delivery_marks_completed_run_task_succeeded(
    migrated_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin, _ = await seed_admin(migrated_db_session)
    complaint = await _seed_complaint_case(migrated_db_session)
    run, task = await _seed_run(
        migrated_db_session,
        complaint_id=complaint.id,
        admin_id=admin.id,
        run_status=WorkflowRunStatus.COMPLETED,
        task_status=BackgroundTaskStatus.RUNNING,
    )
    monkeypatch.setattr(
        workflow_tasks,
        "async_session_factory",
        _session_factory(migrated_db_session),
    )

    result = await run_workflow(run.id, task.id)

    assert result == str(run.id)
    await migrated_db_session.rollback()
    await migrated_db_session.refresh(task)
    await migrated_db_session.refresh(run)
    assert task.status is BackgroundTaskStatus.SUCCEEDED
    assert task.error_message is None
    assert run.status is WorkflowRunStatus.COMPLETED


@pytest.mark.asyncio
async def test_duplicate_delivery_leaves_paused_run_task_unchanged(
    migrated_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin, _ = await seed_admin(migrated_db_session)
    complaint = await _seed_complaint_case(migrated_db_session)
    run, task = await _seed_run(
        migrated_db_session,
        complaint_id=complaint.id,
        admin_id=admin.id,
        run_status=WorkflowRunStatus.PAUSED,
        task_status=BackgroundTaskStatus.RUNNING,
    )
    monkeypatch.setattr(
        workflow_tasks,
        "async_session_factory",
        _session_factory(migrated_db_session),
    )

    result = await run_workflow(run.id, task.id)

    assert result == str(run.id)
    await migrated_db_session.rollback()
    await migrated_db_session.refresh(task)
    await migrated_db_session.refresh(run)
    assert task.status is BackgroundTaskStatus.RUNNING
    assert run.status is WorkflowRunStatus.PAUSED


@pytest.mark.asyncio
async def test_duplicate_delivery_skips_cancelled_task(
    migrated_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin, _ = await seed_admin(migrated_db_session)
    complaint = await _seed_complaint_case(migrated_db_session)
    run, task = await _seed_run(
        migrated_db_session,
        complaint_id=complaint.id,
        admin_id=admin.id,
        run_status=WorkflowRunStatus.COMPLETED,
        task_status=BackgroundTaskStatus.CANCELLED,
    )
    monkeypatch.setattr(
        workflow_tasks,
        "async_session_factory",
        _session_factory(migrated_db_session),
    )

    result = await run_workflow(run.id, task.id)

    assert result == str(run.id)
    await migrated_db_session.rollback()
    await migrated_db_session.refresh(task)
    assert task.status is BackgroundTaskStatus.CANCELLED


@pytest.mark.asyncio
async def test_proposal_crash_boundary_redelivery_recovers_existing_proposal(
    migrated_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin, _ = await seed_admin(migrated_db_session)
    await _seed_skilled_technician(migrated_db_session)
    _, _, complaint = await _seed_ready_complaint(migrated_db_session)
    service = _service(_diagnosis(complaint.id))
    run, task = await _seed_run(
        migrated_db_session,
        complaint_id=complaint.id,
        admin_id=admin.id,
        workflow_type=WorkflowRunType.WORK_ORDER_PROPOSAL,
    )
    run_id = run.id
    task_id = task.id
    complaint_id = complaint.id

    diagnosis = _diagnosis(complaint.id)
    context = await service.validate_generation_context(
        session=migrated_db_session,
        user=admin,
        complaint_id=complaint.id,
    )
    preparation = await service.prepare_generation(
        session=migrated_db_session,
        context=context,
        diagnosis=diagnosis,
    )
    proposal = await service.persist_prepared_proposal(
        session=migrated_db_session,
        user=admin,
        context=context,
        diagnosis=diagnosis,
        preparation=preparation,
        workflow_run_id=run.id,
    )
    await migrated_db_session.commit()
    assert proposal.source_workflow_run_id == run.id
    diagnostic_calls_before = len(service.diagnostic_service.calls)

    monkeypatch.setattr(
        workflow_tasks,
        "async_session_factory",
        _session_factory(migrated_db_session),
    )
    monkeypatch.setattr(
        workflow_tasks,
        "build_diagnostic_service",
        lambda: cast(Any, service.diagnostic_service),
    )
    monkeypatch.setattr(
        workflow_tasks,
        "build_work_order_proposal_service",
        lambda *, diagnostic_service=None: service,
    )
    monkeypatch.setattr(
        workflow_tasks,
        "get_embedding_provider",
        lambda: object(),
    )
    monkeypatch.setattr(
        workflow_tasks,
        "DatabaseVectorIndex",
        _FakeVectorIndex,
    )

    proposal_id = proposal.id
    result = await run_workflow(run_id, task_id)

    assert result == str(run_id)
    await migrated_db_session.rollback()
    migrated_db_session.expire_all()
    refreshed_run = await migrated_db_session.get(WorkflowRun, run_id)
    refreshed_task = await migrated_db_session.get(BackgroundTask, task_id)
    assert refreshed_run is not None
    assert refreshed_run.status is WorkflowRunStatus.COMPLETED
    assert refreshed_run.result_payload == {
        "proposal_id": str(proposal_id),
        "status": "pending_approval",
    }
    assert refreshed_task is not None
    assert refreshed_task.status is BackgroundTaskStatus.SUCCEEDED
    assert len(service.diagnostic_service.calls) == diagnostic_calls_before

    count = await migrated_db_session.scalar(
        select(func.count(WorkOrderProposal.id)).where(
            WorkOrderProposal.complaint_id == complaint_id
        )
    )
    assert count == 1


@pytest.mark.asyncio
async def test_proposal_persistence_failure_does_not_complete_run(
    migrated_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin, _ = await seed_admin(migrated_db_session)
    await _seed_skilled_technician(migrated_db_session)
    _, _, complaint = await _seed_ready_complaint(migrated_db_session)
    service = _service(_diagnosis(complaint.id))
    run, task = await _seed_run(
        migrated_db_session,
        complaint_id=complaint.id,
        admin_id=admin.id,
        workflow_type=WorkflowRunType.WORK_ORDER_PROPOSAL,
    )
    run_id = run.id
    task_id = task.id
    complaint_id = complaint.id
    monkeypatch.setattr(
        workflow_tasks,
        "async_session_factory",
        _session_factory(migrated_db_session),
    )

    async def fail_persist(**kwargs: Any) -> WorkOrderProposal:
        raise ProposalGenerationError("The proposal title is empty.")

    monkeypatch.setattr(service, "persist_prepared_proposal", fail_persist)

    with pytest.raises(WorkflowPermanentError) as exc_info:
        await execute_workflow(
            migrated_db_session,
            workflow_run_id=run_id,
            vector_index=cast(Any, None),
            proposal_service=service,
        )
    await migrated_db_session.rollback()

    assert str(exc_info.value) == (
        "The work-order proposal did not pass validation."
    )
    await _finalize_failed_task(run_id, task_id, exc_info.value)
    await migrated_db_session.rollback()
    migrated_db_session.expire_all()

    refreshed_run = await migrated_db_session.get(WorkflowRun, run_id)
    refreshed_task = await migrated_db_session.get(BackgroundTask, task_id)
    assert refreshed_run is not None
    assert refreshed_run.status is WorkflowRunStatus.FAILED
    assert refreshed_run.error_message == (
        "The work-order proposal did not pass validation."
    )
    assert refreshed_task is not None
    assert refreshed_task.status is BackgroundTaskStatus.FAILED
    assert refreshed_task.error_message == (
        "The work-order proposal did not pass validation."
    )

    count = await migrated_db_session.scalar(
        select(func.count(WorkOrderProposal.id)).where(
            WorkOrderProposal.complaint_id == complaint_id
        )
    )
    assert count == 0


@pytest.mark.asyncio
async def test_concurrent_distinct_runs_create_one_pending_proposal(
    migrated_db_session: AsyncSession,
) -> None:
    admin, _ = await seed_admin(migrated_db_session)
    await _seed_skilled_technician(migrated_db_session)
    _, _, complaint = await _seed_ready_complaint(migrated_db_session)
    service = _service(_diagnosis(complaint.id))
    factory = _session_factory(migrated_db_session)
    complaint_id = complaint.id

    run_ids: list[uuid.UUID] = []
    for _ in range(2):
        run, _ = await _seed_run(
            migrated_db_session,
            complaint_id=complaint_id,
            admin_id=admin.id,
            workflow_type=WorkflowRunType.WORK_ORDER_PROPOSAL,
        )
        run_ids.append(run.id)

    async def execute(run_id: uuid.UUID) -> tuple[str, str | None]:
        async with factory() as session:
            try:
                await execute_workflow(
                    session,
                    workflow_run_id=run_id,
                    vector_index=cast(Any, None),
                    proposal_service=service,
                )
                await session.commit()
                return ("completed", None)
            except Exception as exc:  # noqa: BLE001 - asserted below
                await session.rollback()
                return ("failed", str(exc))

    results = await asyncio.gather(*(execute(run_id) for run_id in run_ids))
    outcomes = sorted(outcome for outcome, _ in results)
    assert outcomes == ["completed", "failed"]

    failed_message = next(message for outcome, message in results if outcome == "failed")
    assert failed_message == "A work order proposal is already pending review."

    await migrated_db_session.rollback()
    migrated_db_session.expire_all()
    proposals = (
        await migrated_db_session.execute(
            select(WorkOrderProposal).where(
                WorkOrderProposal.complaint_id == complaint_id
            )
        )
    ).scalars().all()
    assert len(proposals) == 1
    assert proposals[0].source_workflow_run_id in set(run_ids)

    completed: list[uuid.UUID] = []
    for run_id in run_ids:
        run = await migrated_db_session.get(WorkflowRun, run_id)
        assert run is not None
        if run.status is WorkflowRunStatus.COMPLETED:
            completed.append(run.id)
    assert len(completed) == 1
    assert completed[0] == proposals[0].source_workflow_run_id


@pytest.mark.asyncio
async def test_validate_context_allows_same_run_pending_proposal_only(
    migrated_db_session: AsyncSession,
) -> None:
    admin, _ = await seed_admin(migrated_db_session)
    await _seed_skilled_technician(migrated_db_session)
    _, _, complaint = await _seed_ready_complaint(migrated_db_session)
    service = _service(_diagnosis(complaint.id))
    run, _ = await _seed_run(
        migrated_db_session,
        complaint_id=complaint.id,
        admin_id=admin.id,
        workflow_type=WorkflowRunType.WORK_ORDER_PROPOSAL,
    )
    other_run, _ = await _seed_run(
        migrated_db_session,
        complaint_id=complaint.id,
        admin_id=admin.id,
        workflow_type=WorkflowRunType.WORK_ORDER_PROPOSAL,
    )

    diagnosis = _diagnosis(complaint.id)
    context = await service.validate_generation_context(
        session=migrated_db_session,
        user=admin,
        complaint_id=complaint.id,
    )
    preparation = await service.prepare_generation(
        session=migrated_db_session,
        context=context,
        diagnosis=diagnosis,
    )
    await service.persist_prepared_proposal(
        session=migrated_db_session,
        user=admin,
        context=context,
        diagnosis=diagnosis,
        preparation=preparation,
        workflow_run_id=run.id,
    )
    await migrated_db_session.commit()

    same_run = await service.validate_generation_context(
        session=migrated_db_session,
        user=admin,
        complaint_id=complaint.id,
        workflow_run_id=run.id,
    )
    assert same_run.complaint.id == complaint.id

    with pytest.raises(ProposalAlreadyPendingError):
        await service.validate_generation_context(
            session=migrated_db_session,
            user=admin,
            complaint_id=complaint.id,
            workflow_run_id=other_run.id,
        )


@pytest.mark.asyncio
async def test_retry_exhaustion_leaves_consistent_terminal_state(
    migrated_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin, _ = await seed_admin(migrated_db_session)
    complaint = await _seed_complaint_case(migrated_db_session)
    run, task = await _seed_run(
        migrated_db_session,
        complaint_id=complaint.id,
        admin_id=admin.id,
    )

    async def failing_run_workflow(
        workflow_run_id: uuid.UUID,
        background_task_id: uuid.UUID | None = None,
    ) -> str:
        raise TimeoutError("provider timed out")

    monkeypatch.setattr(workflow_tasks, "run_workflow", failing_run_workflow)
    monkeypatch.setattr(
        workflow_tasks,
        "async_session_factory",
        _session_factory(migrated_db_session),
    )

    fake_task = SimpleNamespace(
        request=SimpleNamespace(retries=settings.celery_task_max_retries),
        retry=lambda **_kwargs: pytest.fail("exhausted task must not retry"),
    )
    run_id = run.id
    task_id = task.id

    with pytest.raises(TimeoutError):
        await asyncio.to_thread(_execute_task, fake_task, str(run_id), str(task_id))

    await migrated_db_session.rollback()
    migrated_db_session.expire_all()
    refreshed_run = await migrated_db_session.get(WorkflowRun, run_id)
    refreshed_task = await migrated_db_session.get(BackgroundTask, task_id)
    assert refreshed_run is not None
    assert refreshed_run.status is WorkflowRunStatus.FAILED
    assert refreshed_run.error_message == GENERIC_WORKFLOW_ERROR
    assert refreshed_task is not None
    assert refreshed_task.status is BackgroundTaskStatus.FAILED
    assert refreshed_task.error_message == GENERIC_WORKFLOW_ERROR


@pytest.mark.asyncio
async def test_transient_failure_below_limit_is_retried(
    migrated_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin, _ = await seed_admin(migrated_db_session)
    complaint = await _seed_complaint_case(migrated_db_session)
    run, task = await _seed_run(
        migrated_db_session,
        complaint_id=complaint.id,
        admin_id=admin.id,
    )

    async def failing_run_workflow(
        workflow_run_id: uuid.UUID,
        background_task_id: uuid.UUID | None = None,
    ) -> str:
        raise TimeoutError("provider timed out")

    monkeypatch.setattr(workflow_tasks, "run_workflow", failing_run_workflow)
    monkeypatch.setattr(
        workflow_tasks,
        "async_session_factory",
        _session_factory(migrated_db_session),
    )

    retry_calls: list[int] = []

    def retry(*, countdown: int, **_kwargs: object) -> None:
        retry_calls.append(countdown)
        raise RuntimeError("retry requested")

    fake_task = SimpleNamespace(
        request=SimpleNamespace(retries=0),
        retry=retry,
    )
    run_id = run.id
    task_id = task.id

    with pytest.raises(RuntimeError, match="retry requested"):
        await asyncio.to_thread(_execute_task, fake_task, str(run_id), str(task_id))

    assert retry_calls == [settings.celery_task_retry_backoff_seconds]
    await migrated_db_session.rollback()
    refreshed_run = await migrated_db_session.get(WorkflowRun, run_id)
    refreshed_task = await migrated_db_session.get(BackgroundTask, task_id)
    assert refreshed_run is not None
    assert refreshed_run.status is WorkflowRunStatus.RUNNING
    assert refreshed_run.error_message is None
    assert refreshed_task is not None
    assert refreshed_task.status is BackgroundTaskStatus.PENDING


@pytest.mark.asyncio
async def test_queued_running_status_semantics_at_scheduling(
    migrated_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin, _ = await seed_admin(migrated_db_session)
    complaint = await _seed_complaint_case(migrated_db_session)
    monkeypatch.setattr(settings, "celery_task_always_eager", False)

    pending = await schedule_diagnostic_investigation(
        migrated_db_session,
        user=admin,
        complaint_id=complaint.id,
        focus="Check the DC input fuse.",
    )

    run = pending.workflow_run
    assert run.status is WorkflowRunStatus.RUNNING
    assert run.current_step == "queued"
    task = await migrated_db_session.get(
        BackgroundTask,
        pending.background_task_id,
    )
    event = await migrated_db_session.get(
        OutboxEvent,
        pending.outbox_event_id,
    )
    assert task is not None
    assert task.status is BackgroundTaskStatus.PENDING
    assert event is not None
    assert event.status is OutboxEventStatus.PENDING


@pytest.mark.asyncio
async def test_accept_response_reports_queued_without_running_model(
    api_client: Any,
    migrated_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _admin, admin_token = await seed_admin(migrated_db_session)
    complaint = await _seed_complaint_case(migrated_db_session)
    stub = StubDiagnosticService(result=_diagnosis(complaint.id))
    app.dependency_overrides[get_diagnostic_service] = lambda: stub
    monkeypatch.setattr(settings, "celery_task_always_eager", False)

    async def deferred_dispatch(session: AsyncSession, event_id: uuid.UUID) -> bool:
        return False

    monkeypatch.setattr(scheduling, "dispatch_outbox_event", deferred_dispatch)

    response = await api_client.post(
        "/api/v1/diagnostics/investigate",
        headers=bearer(admin_token),
        json={"complaint_id": str(complaint.id), "focus": "Check E-05"},
    )

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "running"
    assert body["current_step"] == "queued"
    assert stub.calls == []


@pytest.mark.asyncio
async def test_concurrent_duplicate_delivery_of_same_task_executes_once(
    committed_migration_database: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_async_engine(
        committed_migration_database.url,
        poolclass=NullPool,
    )
    factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    try:
        async with factory() as setup:
            admin, _ = await seed_admin(setup)
            _, customer, _ = await seed_customer(setup)
            equipment = await seed_equipment(setup, customer)
            complaint = await seed_complaint(
                setup,
                customer,
                equipment=equipment,
            )
            run, task = await _seed_run(
                setup,
                complaint_id=complaint.id,
                admin_id=admin.id,
            )
            run_id = run.id
            task_id = task.id
            complaint_id = complaint.id

        entered = asyncio.Event()
        release = asyncio.Event()
        stub = _BlockingDiagnosticService(
            _diagnosis(complaint_id),
            entered,
            release,
        )
        monkeypatch.setattr(
            workflow_tasks,
            "async_session_factory",
            factory,
        )
        monkeypatch.setattr(
            workflow_tasks,
            "build_diagnostic_service",
            lambda: stub,
        )
        monkeypatch.setattr(
            workflow_tasks,
            "build_work_order_proposal_service",
            lambda *, diagnostic_service=None: SimpleNamespace(
                diagnostic_service=diagnostic_service
            ),
        )
        monkeypatch.setattr(
            workflow_tasks,
            "get_embedding_provider",
            lambda: object(),
        )
        monkeypatch.setattr(
            workflow_tasks,
            "DatabaseVectorIndex",
            _FakeVectorIndex,
        )

        first = asyncio.create_task(run_workflow(run_id, task_id))
        await asyncio.wait_for(entered.wait(), timeout=10)

        with pytest.raises(WorkflowExecutionBusyError) as exc_info:
            await run_workflow(run_id, task_id)
        assert exc_info.value.retry_after_seconds >= 1
        assert stub.executions == 1

        release.set()
        assert await asyncio.wait_for(first, timeout=20) == str(run_id)

        async with factory() as verify:
            completed_run = await verify.get(WorkflowRun, run_id)
            completed_task = await verify.get(BackgroundTask, task_id)
            assert completed_run is not None
            assert completed_run.status is WorkflowRunStatus.COMPLETED
            assert completed_run.result_payload is not None
            assert completed_task is not None
            assert completed_task.status is BackgroundTaskStatus.SUCCEEDED
            assert completed_task.attempts == 1

        assert await run_workflow(run_id, task_id) == str(run_id)

        async with factory() as verify:
            redelivered_task = await verify.get(BackgroundTask, task_id)
            assert redelivered_task is not None
            assert redelivered_task.status is BackgroundTaskStatus.SUCCEEDED
            assert redelivered_task.attempts == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_worker_that_lost_claim_cannot_advance_workflow(
    committed_migration_database: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_async_engine(
        committed_migration_database.url,
        poolclass=NullPool,
    )
    factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    try:
        async with factory() as setup:
            admin, _ = await seed_admin(setup)
            _, customer, _ = await seed_customer(setup)
            equipment = await seed_equipment(setup, customer)
            complaint = await seed_complaint(
                setup,
                customer,
                equipment=equipment,
            )
            run, task = await _seed_run(
                setup,
                complaint_id=complaint.id,
                admin_id=admin.id,
            )
            run_id = run.id
            task_id = task.id
            complaint_id = complaint.id

        entered = asyncio.Event()
        release = asyncio.Event()
        stub = _BlockingDiagnosticService(
            _diagnosis(complaint_id),
            entered,
            release,
        )
        monkeypatch.setattr(
            workflow_tasks,
            "async_session_factory",
            factory,
        )
        monkeypatch.setattr(
            workflow_tasks,
            "build_diagnostic_service",
            lambda: stub,
        )
        monkeypatch.setattr(
            workflow_tasks,
            "build_work_order_proposal_service",
            lambda *, diagnostic_service=None: SimpleNamespace(
                diagnostic_service=diagnostic_service
            ),
        )
        monkeypatch.setattr(
            workflow_tasks,
            "get_embedding_provider",
            lambda: object(),
        )
        monkeypatch.setattr(
            workflow_tasks,
            "DatabaseVectorIndex",
            _FakeVectorIndex,
        )

        first = asyncio.create_task(run_workflow(run_id, task_id))
        await asyncio.wait_for(entered.wait(), timeout=10)

        async with factory() as takeover:
            claimed_task = await takeover.get(BackgroundTask, task_id)
            assert claimed_task is not None
            assert claimed_task.started_at is not None
            takeover_started_at = claimed_task.started_at + timedelta(seconds=1)
            claimed_task.started_at = takeover_started_at
            await takeover.commit()

        release.set()
        assert await asyncio.wait_for(first, timeout=20) == str(run_id)

        async with factory() as verify:
            run = await verify.get(WorkflowRun, run_id)
            task = await verify.get(BackgroundTask, task_id)
            assert run is not None
            assert run.status is WorkflowRunStatus.RUNNING
            assert run.current_step == "investigating"
            assert task is not None
            assert task.status is BackgroundTaskStatus.RUNNING
            assert task.started_at == takeover_started_at
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_duplicate_proposal_task_persists_one_proposal(
    committed_migration_database: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_async_engine(
        committed_migration_database.url,
        poolclass=NullPool,
    )
    factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    try:
        async with factory() as setup:
            admin, _ = await seed_admin(setup)
            await _seed_skilled_technician(setup)
            _, _, complaint = await _seed_ready_complaint(setup)
            service = _service(_diagnosis(complaint.id))
            run, task = await _seed_run(
                setup,
                complaint_id=complaint.id,
                admin_id=admin.id,
                workflow_type=WorkflowRunType.WORK_ORDER_PROPOSAL,
            )
            run_id = run.id
            task_id = task.id
            complaint_id = complaint.id

        entered = asyncio.Event()
        release = asyncio.Event()
        proposal_executions: list[int] = []
        original_run_agent = service.diagnostic_service.run_agent

        async def blocking_run_agent(**kwargs: Any) -> Any:
            proposal_executions.append(1)
            entered.set()
            await release.wait()
            return await original_run_agent(**kwargs)

        monkeypatch.setattr(
            service.diagnostic_service,
            "run_agent",
            blocking_run_agent,
        )
        monkeypatch.setattr(
            workflow_tasks,
            "async_session_factory",
            factory,
        )
        monkeypatch.setattr(
            workflow_tasks,
            "build_diagnostic_service",
            lambda: service.diagnostic_service,
        )
        monkeypatch.setattr(
            workflow_tasks,
            "build_work_order_proposal_service",
            lambda *, diagnostic_service=None: service,
        )
        monkeypatch.setattr(
            workflow_tasks,
            "get_embedding_provider",
            lambda: object(),
        )
        monkeypatch.setattr(
            workflow_tasks,
            "DatabaseVectorIndex",
            _FakeVectorIndex,
        )

        first = asyncio.create_task(run_workflow(run_id, task_id))
        await asyncio.wait_for(entered.wait(), timeout=10)

        with pytest.raises(WorkflowExecutionBusyError):
            await run_workflow(run_id, task_id)
        assert proposal_executions == [1]

        release.set()
        assert await asyncio.wait_for(first, timeout=20) == str(run_id)

        async with factory() as verify:
            completed_run = await verify.get(WorkflowRun, run_id)
            completed_task = await verify.get(BackgroundTask, task_id)
            proposal_count = await verify.scalar(
                select(func.count(WorkOrderProposal.id)).where(
                    WorkOrderProposal.complaint_id == complaint_id
                )
            )
            proposals = (
                await verify.execute(
                    select(WorkOrderProposal).where(
                        WorkOrderProposal.complaint_id == complaint_id
                    )
                )
            ).scalars().all()
            assert completed_run is not None
            assert completed_run.status is WorkflowRunStatus.COMPLETED
            assert completed_task is not None
            assert completed_task.status is BackgroundTaskStatus.SUCCEEDED
            assert proposal_count == 1
            assert len(proposals) == 1
            assert proposals[0].source_workflow_run_id == run_id

        assert await run_workflow(run_id, task_id) == str(run_id)

        async with factory() as verify:
            proposal_count = await verify.scalar(
                select(func.count(WorkOrderProposal.id)).where(
                    WorkOrderProposal.complaint_id == complaint_id
                )
            )
            assert proposal_count == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_stale_running_claim_can_be_recovered_after_safe_window(
    committed_migration_database: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_async_engine(
        committed_migration_database.url,
        poolclass=NullPool,
    )
    factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    try:
        stale = datetime.now(UTC) - timedelta(hours=2)
        async with factory() as setup:
            admin, _ = await seed_admin(setup)
            _, customer, _ = await seed_customer(setup)
            equipment = await seed_equipment(setup, customer)
            complaint = await seed_complaint(
                setup,
                customer,
                equipment=equipment,
            )
            run, task = await _seed_run(
                setup,
                complaint_id=complaint.id,
                admin_id=admin.id,
                task_status=BackgroundTaskStatus.RUNNING,
            )
            task.started_at = stale
            task.attempts = 1
            await setup.commit()
            run_id = run.id
            task_id = task.id
            complaint_id = complaint.id

        stub = StubDiagnosticService(_diagnosis(complaint_id))
        monkeypatch.setattr(
            workflow_tasks,
            "async_session_factory",
            factory,
        )
        monkeypatch.setattr(
            workflow_tasks,
            "build_diagnostic_service",
            lambda: stub,
        )
        monkeypatch.setattr(
            workflow_tasks,
            "build_work_order_proposal_service",
            lambda *, diagnostic_service=None: SimpleNamespace(
                diagnostic_service=diagnostic_service
            ),
        )
        monkeypatch.setattr(
            workflow_tasks,
            "get_embedding_provider",
            lambda: object(),
        )
        monkeypatch.setattr(
            workflow_tasks,
            "DatabaseVectorIndex",
            _FakeVectorIndex,
        )

        assert await run_workflow(run_id, task_id) == str(run_id)

        async with factory() as verify:
            recovered_run = await verify.get(WorkflowRun, run_id)
            recovered_task = await verify.get(BackgroundTask, task_id)
            assert recovered_run is not None
            assert recovered_run.status is WorkflowRunStatus.COMPLETED
            assert recovered_task is not None
            assert recovered_task.status is BackgroundTaskStatus.SUCCEEDED
            assert recovered_task.attempts == 2
            assert recovered_task.started_at is not None
            assert recovered_task.started_at > stale
    finally:
        await engine.dispose()
