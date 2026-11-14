from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from typing import Any, cast

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.db.session import run_async_task
from app.models.background_task import BackgroundTask
from app.models.enums import (
    BackgroundTaskStatus,
    WorkflowRunStatus,
    WorkflowRunType,
)
from app.models.workflow_run import WorkflowRun
from app.services.diagnostics.diagnostics import DiagnosticService
from app.services.tasks.execution import (
    DIAGNOSTIC_INVESTIGATION_TASK_NAME,
    WORK_ORDER_PROPOSAL_TASK_NAME,
    create_background_task,
)
from app.services.work_orders.work_order_proposals import (
    WorkOrderProposalService,
)
from app.services.workflows.errors import WorkflowPermanentError
from app.tasks import workflows as workflow_tasks
from app.tasks.workflows import _execute_task, _finalize_failed_task
from tests.conftest import MigrationDatabase
from tests.services.work_orders.test_work_order_proposals import (
    StubDiagnosticService,
    _agent_builder,
    _diagnosis,
    _draft,
    _seed_ready_complaint,
    _seed_skilled_technician,
)
from tests.support import (
    seed_admin,
    seed_complaint,
    seed_customer,
    seed_equipment,
)


class _FakeVectorIndex:
    def __init__(self, **kwargs: object) -> None:
        pass

    async def close(self) -> None:
        return None


class _FailingDiagnosticService(StubDiagnosticService):
    def __init__(self, error: BaseException) -> None:
        super().__init__(_diagnosis(uuid.uuid4()))
        self._error = error

    async def run_agent(self, **kwargs: Any) -> Any:
        raise self._error


class _ComplaintAwareDiagnosticService(StubDiagnosticService):
    def __init__(self) -> None:
        super().__init__(_diagnosis(uuid.uuid4()))

    def finalize(self, **kwargs: Any) -> Any:
        return _diagnosis(kwargs["preparation"].complaint.id)


class _RetryRequested(RuntimeError):
    pass


class _FakeCeleryTask:
    def __init__(self, retries: int = 0) -> None:
        self.request = SimpleNamespace(retries=retries)
        self.retry_countdowns: list[int] = []

    def retry(self, *, countdown: int, **_kwargs: object) -> None:
        self.retry_countdowns.append(countdown)
        raise _RetryRequested("retry requested")


def _worker_engine(url: str) -> AsyncEngine:
    return create_async_engine(
        url,
        pool_size=1,
        max_overflow=0,
        pool_timeout=5,
        pool_pre_ping=True,
        connect_args={"timeout": 5},
    )


def _factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


async def _seed_diagnostic_runs(
    database: MigrationDatabase,
    *,
    count: int,
) -> tuple[uuid.UUID, uuid.UUID, list[tuple[uuid.UUID, uuid.UUID]]]:
    engine = create_async_engine(database.url, poolclass=NullPool)
    factory = _factory(engine)
    try:
        async with factory() as session:
            admin, _ = await seed_admin(session)
            _, customer, _ = await seed_customer(session)
            equipment = await seed_equipment(session, customer)
            complaint = await seed_complaint(
                session,
                customer,
                equipment=equipment,
            )
            run_ids: list[tuple[uuid.UUID, uuid.UUID]] = []
            for _ in range(count):
                run = WorkflowRun(
                    complaint_id=complaint.id,
                    workflow_type=WorkflowRunType.DIAGNOSTIC_INVESTIGATION,
                    requested_by_id=admin.id,
                    status=WorkflowRunStatus.RUNNING,
                    current_step="queued",
                )
                session.add(run)
                await session.flush()
                task = create_background_task(
                    task_name=DIAGNOSTIC_INVESTIGATION_TASK_NAME,
                    celery_task_id=str(uuid.uuid4()),
                    resource_type="workflow_run",
                    resource_id=run.id,
                )
                session.add(task)
                await session.flush()
                run_ids.append((run.id, task.id))
            await session.commit()
            return admin.id, complaint.id, run_ids
    finally:
        await engine.dispose()


async def _seed_proposal_runs(
    database: MigrationDatabase,
    *,
    count: int,
) -> tuple[uuid.UUID, list[tuple[uuid.UUID, uuid.UUID]]]:
    engine = create_async_engine(database.url, poolclass=NullPool)
    factory = _factory(engine)
    try:
        async with factory() as session:
            admin, _ = await seed_admin(session)
            await _seed_skilled_technician(session)
            run_ids: list[tuple[uuid.UUID, uuid.UUID]] = []
            for _ in range(count):
                _, _, complaint = await _seed_ready_complaint(session)
                run = WorkflowRun(
                    complaint_id=complaint.id,
                    workflow_type=WorkflowRunType.WORK_ORDER_PROPOSAL,
                    requested_by_id=admin.id,
                    status=WorkflowRunStatus.RUNNING,
                    current_step="queued",
                )
                session.add(run)
                await session.flush()
                task = create_background_task(
                    task_name=WORK_ORDER_PROPOSAL_TASK_NAME,
                    celery_task_id=str(uuid.uuid4()),
                    resource_type="workflow_run",
                    resource_id=run.id,
                )
                session.add(task)
                await session.flush()
                run_ids.append((run.id, task.id))
            await session.commit()
            return admin.id, run_ids
    finally:
        await engine.dispose()


async def _read_states(
    database: MigrationDatabase,
    pairs: list[tuple[uuid.UUID, uuid.UUID]],
) -> list[tuple[WorkflowRun | None, BackgroundTask | None]]:
    engine = create_async_engine(database.url, poolclass=NullPool)
    factory = _factory(engine)
    try:
        async with factory() as session:
            return [
                (
                    await session.get(WorkflowRun, run_id),
                    await session.get(BackgroundTask, task_id),
                )
                for run_id, task_id in pairs
            ]
    finally:
        await engine.dispose()


def _patch_workflow_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    engine: AsyncEngine,
    factory: async_sessionmaker[AsyncSession],
    *,
    diagnostic_service: Any,
    proposal_service: Any = None,
) -> None:
    monkeypatch.setattr(workflow_tasks, "engine", engine)
    monkeypatch.setattr(workflow_tasks, "async_session_factory", factory)
    monkeypatch.setattr(workflow_tasks, "DatabaseVectorIndex", _FakeVectorIndex)
    monkeypatch.setattr(
        workflow_tasks,
        "get_embedding_provider",
        lambda: object(),
    )
    monkeypatch.setattr(
        workflow_tasks,
        "build_diagnostic_service",
        lambda: diagnostic_service,
    )
    monkeypatch.setattr(
        workflow_tasks,
        "build_work_order_proposal_service",
        lambda *, diagnostic_service=None: (
            proposal_service
            if proposal_service is not None
            else SimpleNamespace(diagnostic_service=diagnostic_service)
        ),
    )


def _proposal_service(
    diagnostic_service: DiagnosticService,
) -> WorkOrderProposalService:
    return WorkOrderProposalService(
        diagnostic_service=diagnostic_service,
        chat_model_factory=lambda: cast(Any, object()),
        max_tool_calls=3,
        max_model_calls=3,
        technician_limit=100,
        agent_builder=_agent_builder(_draft()),
    )


def test_two_sequential_diagnostic_tasks_succeed_in_same_process(
    committed_migration_database: MigrationDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, complaint_id, pairs = asyncio.run(
        _seed_diagnostic_runs(committed_migration_database, count=2)
    )
    engine = _worker_engine(committed_migration_database.url)
    factory = _factory(engine)
    _patch_workflow_dependencies(
        monkeypatch,
        engine,
        factory,
        diagnostic_service=StubDiagnosticService(_diagnosis(complaint_id)),
    )
    try:
        first_run, first_task = pairs[0]
        second_run, second_task = pairs[1]

        assert _execute_task(
            _FakeCeleryTask(),
            str(first_run),
            str(first_task),
        ) == str(first_run)

        assert _execute_task(
            _FakeCeleryTask(),
            str(second_run),
            str(second_task),
        ) == str(second_run)
    finally:
        asyncio.run(engine.dispose())

    states = asyncio.run(_read_states(committed_migration_database, pairs))
    assert [state[0].status for state in states if state[0]] == [
        WorkflowRunStatus.COMPLETED,
        WorkflowRunStatus.COMPLETED,
    ]
    assert [state[1].status for state in states if state[1]] == [
        BackgroundTaskStatus.SUCCEEDED,
        BackgroundTaskStatus.SUCCEEDED,
    ]
    assert [state[1].attempts for state in states if state[1]] == [1, 1]


def test_two_sequential_proposal_tasks_succeed_in_same_process(
    committed_migration_database: MigrationDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, pairs = asyncio.run(
        _seed_proposal_runs(committed_migration_database, count=2)
    )
    engine = _worker_engine(committed_migration_database.url)
    factory = _factory(engine)
    diagnostic_service = _ComplaintAwareDiagnosticService()
    _patch_workflow_dependencies(
        monkeypatch,
        engine,
        factory,
        diagnostic_service=diagnostic_service,
        proposal_service=_proposal_service(
            cast(DiagnosticService, diagnostic_service)
        ),
    )
    try:
        for run_id, task_id in pairs:
            assert _execute_task(
                _FakeCeleryTask(),
                str(run_id),
                str(task_id),
            ) == str(run_id)
    finally:
        asyncio.run(engine.dispose())

    states = asyncio.run(_read_states(committed_migration_database, pairs))
    for run, task in states:
        assert run is not None
        assert run.status is WorkflowRunStatus.COMPLETED
        assert task is not None
        assert task.status is BackgroundTaskStatus.SUCCEEDED
        assert task.attempts == 1


def test_first_task_failure_does_not_break_second_task(
    committed_migration_database: MigrationDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, complaint_id, pairs = asyncio.run(
        _seed_diagnostic_runs(committed_migration_database, count=2)
    )
    engine = _worker_engine(committed_migration_database.url)
    factory = _factory(engine)
    services: dict[str, Any] = {
        "current": _FailingDiagnosticService(RuntimeError("agent failed")),
    }
    _patch_workflow_dependencies(
        monkeypatch,
        engine,
        factory,
        diagnostic_service=None,
    )
    monkeypatch.setattr(
        workflow_tasks,
        "build_diagnostic_service",
        lambda: services["current"],
    )
    try:
        first_run, first_task = pairs[0]
        with pytest.raises(WorkflowPermanentError):
            _execute_task(
                _FakeCeleryTask(),
                str(first_run),
                str(first_task),
            )

        services["current"] = StubDiagnosticService(_diagnosis(complaint_id))
        second_run, second_task = pairs[1]
        assert _execute_task(
            _FakeCeleryTask(),
            str(second_run),
            str(second_task),
        ) == str(second_run)
    finally:
        asyncio.run(engine.dispose())

    states = asyncio.run(_read_states(committed_migration_database, pairs))
    assert states[0][0] is not None
    assert states[0][0].status is WorkflowRunStatus.FAILED
    assert states[0][1] is not None
    assert states[0][1].status is BackgroundTaskStatus.FAILED
    assert states[1][0] is not None
    assert states[1][0].status is WorkflowRunStatus.COMPLETED
    assert states[1][1] is not None
    assert states[1][1].status is BackgroundTaskStatus.SUCCEEDED


def test_transient_failure_is_retried_in_same_process(
    committed_migration_database: MigrationDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, complaint_id, pairs = asyncio.run(
        _seed_diagnostic_runs(committed_migration_database, count=1)
    )
    run_id, task_id = pairs[0]
    engine = _worker_engine(committed_migration_database.url)
    factory = _factory(engine)
    services: dict[str, Any] = {
        "current": _FailingDiagnosticService(TimeoutError("provider timed out")),
    }
    _patch_workflow_dependencies(
        monkeypatch,
        engine,
        factory,
        diagnostic_service=None,
    )
    monkeypatch.setattr(
        workflow_tasks,
        "build_diagnostic_service",
        lambda: services["current"],
    )
    try:
        first_attempt = _FakeCeleryTask(retries=0)
        with pytest.raises(_RetryRequested):
            _execute_task(
                first_attempt,
                str(run_id),
                str(task_id),
            )
        assert len(first_attempt.retry_countdowns) == 1

        pending = asyncio.run(_read_states(committed_migration_database, pairs))
        assert pending[0][0] is not None
        assert pending[0][0].status is WorkflowRunStatus.RUNNING
        assert pending[0][1] is not None
        assert pending[0][1].status is BackgroundTaskStatus.PENDING

        services["current"] = StubDiagnosticService(_diagnosis(complaint_id))
        assert _execute_task(
            _FakeCeleryTask(retries=1),
            str(run_id),
            str(task_id),
        ) == str(run_id)
    finally:
        asyncio.run(engine.dispose())

    states = asyncio.run(_read_states(committed_migration_database, pairs))
    assert states[0][0] is not None
    assert states[0][0].status is WorkflowRunStatus.COMPLETED
    assert states[0][1] is not None
    assert states[0][1].status is BackgroundTaskStatus.SUCCEEDED
    assert states[0][1].attempts == 2


def test_preclaim_infrastructure_failure_does_not_finalize_task(
    committed_migration_database: MigrationDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, pairs = asyncio.run(
        _seed_diagnostic_runs(committed_migration_database, count=1)
    )
    run_id, task_id = pairs[0]
    engine = _worker_engine(committed_migration_database.url)
    factory = _factory(engine)
    _patch_workflow_dependencies(
        monkeypatch,
        engine,
        factory,
        diagnostic_service=None,
    )

    async def failing_before_claim(
        workflow_run_id: uuid.UUID,
        background_task_id: uuid.UUID | None = None,
    ) -> str:
        raise RuntimeError("database pool is unusable")

    monkeypatch.setattr(workflow_tasks, "run_workflow", failing_before_claim)
    try:
        fake_task = _FakeCeleryTask(retries=0)
        with pytest.raises(_RetryRequested):
            _execute_task(fake_task, str(run_id), str(task_id))
        assert len(fake_task.retry_countdowns) == 1
    finally:
        asyncio.run(engine.dispose())

    states = asyncio.run(_read_states(committed_migration_database, pairs))
    assert states[0][0] is not None
    assert states[0][0].status is WorkflowRunStatus.RUNNING
    assert states[0][0].error_message is None
    assert states[0][1] is not None
    assert states[0][1].status is BackgroundTaskStatus.PENDING
    assert states[0][1].attempts == 0


def test_unclaimed_finalization_does_not_overwrite_live_claim(
    committed_migration_database: MigrationDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, pairs = asyncio.run(
        _seed_diagnostic_runs(committed_migration_database, count=1)
    )
    run_id, task_id = pairs[0]
    engine = create_async_engine(
        committed_migration_database.url,
        poolclass=NullPool,
    )
    factory = _factory(engine)
    monkeypatch.setattr(workflow_tasks, "engine", engine)
    monkeypatch.setattr(workflow_tasks, "async_session_factory", factory)

    async def claim_as_other_worker() -> None:
        async with factory() as session:
            task = await session.get(BackgroundTask, task_id)
            assert task is not None
            task.status = BackgroundTaskStatus.RUNNING
            task.started_at = task.created_at
            task.attempts = 1
            await session.commit()

    asyncio.run(claim_as_other_worker())
    try:
        asyncio.run(
            _finalize_failed_task(
                run_id,
                task_id,
                RuntimeError("unclaimed infrastructure failure"),
                claimed_started_at=None,
            )
        )
    finally:
        asyncio.run(engine.dispose())

    states = asyncio.run(_read_states(committed_migration_database, pairs))
    assert states[0][0] is not None
    assert states[0][0].status is WorkflowRunStatus.RUNNING
    assert states[0][1] is not None
    assert states[0][1].status is BackgroundTaskStatus.RUNNING
    assert states[0][1].attempts == 1


def test_run_async_task_disposes_engine_before_loop_shutdown(
    committed_migration_database: MigrationDatabase,
) -> None:
    engine = _worker_engine(committed_migration_database.url)
    factory = _factory(engine)
    events: list[str] = []
    closed_during_dispose: list[bool] = []

    @event.listens_for(engine.sync_engine, "checkin")
    def _on_checkin(*_args: object) -> None:
        events.append("checkin")

    @event.listens_for(engine.sync_engine, "close")
    def _on_close(*_args: object) -> None:
        events.append("close")
        closed_during_dispose.append(asyncio.get_running_loop().is_closed())

    async def first_query() -> str:
        async with factory() as session:
            await session.execute(text("SELECT 1"))
            await session.commit()
        return "first"

    async def second_query() -> str:
        async with factory() as session:
            await session.execute(text("SELECT 1"))
            await session.commit()
        return "second"

    try:
        assert run_async_task(first_query(), engine=engine) == "first"
        assert "checkin" in events
        assert "close" in events
        assert events.index("checkin") < events.index("close")
        assert closed_during_dispose
        assert not any(closed_during_dispose)
        pool = cast(Any, engine.pool)
        assert pool.checkedin() == 0
        assert pool.checkedout() == 0

        assert run_async_task(second_query(), engine=engine) == "second"
    finally:
        asyncio.run(engine.dispose())
