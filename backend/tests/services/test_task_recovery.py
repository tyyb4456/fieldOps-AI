from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.models.background_task import BackgroundTask
from app.models.document import Document
from app.models.enums import (
    BackgroundTaskStatus,
    IngestionStatus,
    OutboxEventStatus,
    WorkflowRunStatus,
    WorkflowRunType,
)
from app.models.outbox_event import OutboxEvent
from app.models.workflow_run import WorkflowRun
from app.services.tasks import outbox
from app.services.tasks.recovery import (
    RECONCILED_DOCUMENT_ERROR,
    RECONCILED_OUTBOX_ERROR,
    RECONCILED_RUNNING_TASK_ERROR,
    RECONCILED_RUNNING_WORKFLOW_ERROR,
    RECONCILED_TASK_ERROR,
    fail_stale_pending_tasks,
    fail_stale_running_tasks,
    inspect_background_tasks,
)
from tests.support import (
    seed_admin,
    seed_complaint,
    seed_customer,
    seed_equipment,
)


def _document(*, status: IngestionStatus) -> Document:
    return Document(
        manufacturer="Acme Solar",
        model="INV-5000",
        document_name=f"Manual {uuid.uuid4().hex}",
        version="1.0",
        storage_key=f"documents/{uuid.uuid4().hex}.pdf",
        ingestion_status=status,
    )


def _task(
    *,
    status: BackgroundTaskStatus,
    created_at: datetime,
    resource_id: uuid.UUID | None = None,
    started_at: datetime | None = None,
) -> BackgroundTask:
    task = BackgroundTask(
        task_name="documents.ingest_document",
        celery_task_id=str(uuid.uuid4()),
        status=status,
        resource_type="document" if resource_id is not None else None,
        resource_id=resource_id,
        started_at=started_at,
    )
    task.created_at = created_at
    return task


def _outbox_event_for(
    task: BackgroundTask,
    document: Document,
) -> OutboxEvent:
    return outbox.create_outbox_event(
        event_type=task.task_name,
        payload={
            "document_id": str(document.id),
            "background_task_id": str(task.id),
            "celery_task_id": task.celery_task_id,
        },
    )


async def test_inspect_reports_stale_state(
    migrated_db_session: AsyncSession,
) -> None:
    stale = datetime.now(UTC) - timedelta(hours=2)
    pending_doc = _document(status=IngestionStatus.PENDING)
    processing_doc = _document(status=IngestionStatus.PROCESSING)
    migrated_db_session.add_all([pending_doc, processing_doc])
    await migrated_db_session.flush()

    stale_pending_task = _task(
        status=BackgroundTaskStatus.PENDING,
        created_at=stale,
        resource_id=pending_doc.id,
    )
    stale_running_task = _task(
        status=BackgroundTaskStatus.RUNNING,
        created_at=stale,
        started_at=stale,
    )
    fresh_task = _task(
        status=BackgroundTaskStatus.PENDING,
        created_at=datetime.now(UTC),
    )
    pending_event = outbox.create_outbox_event(
        event_type="documents.ingest_document",
        payload={"document_id": str(pending_doc.id)},
    )
    failed_event = outbox.create_outbox_event(
        event_type="documents.ingest_document",
        payload={"document_id": str(pending_doc.id)},
    )
    failed_event.status = OutboxEventStatus.FAILED
    migrated_db_session.add_all(
        [
            stale_pending_task,
            stale_running_task,
            fresh_task,
            pending_event,
            failed_event,
        ]
    )
    await migrated_db_session.commit()

    report = await inspect_background_tasks(
        migrated_db_session,
        stale_after_seconds=3600,
    )

    assert report.stale_pending_tasks == (stale_pending_task.id,)
    assert report.stale_running_tasks == (stale_running_task.id,)
    assert report.pending_outbox_events == 1
    assert report.failed_outbox_events == 1
    assert processing_doc.id in report.processing_documents
    assert not report.healthy


async def test_fail_stale_pending_tasks_never_touches_running_or_fresh(
    migrated_db_session: AsyncSession,
) -> None:
    stale = datetime.now(UTC) - timedelta(hours=2)
    pending_doc = _document(status=IngestionStatus.PENDING)
    processing_doc = _document(status=IngestionStatus.PROCESSING)
    migrated_db_session.add_all([pending_doc, processing_doc])
    await migrated_db_session.flush()

    stale_pending_task = _task(
        status=BackgroundTaskStatus.PENDING,
        created_at=stale,
        resource_id=pending_doc.id,
    )
    stale_running_task = _task(
        status=BackgroundTaskStatus.RUNNING,
        created_at=stale,
        started_at=stale,
        resource_id=processing_doc.id,
    )
    fresh_task = _task(
        status=BackgroundTaskStatus.PENDING,
        created_at=datetime.now(UTC),
    )
    migrated_db_session.add_all(
        [stale_pending_task, stale_running_task, fresh_task]
    )
    await migrated_db_session.commit()

    reconciled = await fail_stale_pending_tasks(
        migrated_db_session,
        stale_after_seconds=3600,
    )

    assert reconciled == (stale_pending_task.id,)

    await migrated_db_session.refresh(stale_pending_task)
    assert stale_pending_task.status is BackgroundTaskStatus.FAILED
    assert stale_pending_task.error_message == RECONCILED_TASK_ERROR

    await migrated_db_session.refresh(stale_running_task)
    assert stale_running_task.status is BackgroundTaskStatus.RUNNING

    await migrated_db_session.refresh(fresh_task)
    assert fresh_task.status is BackgroundTaskStatus.PENDING

    await migrated_db_session.refresh(pending_doc)
    assert pending_doc.ingestion_status is IngestionStatus.FAILED
    assert pending_doc.ingestion_error == RECONCILED_DOCUMENT_ERROR

    await migrated_db_session.refresh(processing_doc)
    assert processing_doc.ingestion_status is IngestionStatus.PROCESSING


async def test_fail_stale_pending_tasks_fails_pending_outbox_event(
    migrated_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stale = datetime.now(UTC) - timedelta(hours=2)
    document = _document(status=IngestionStatus.PENDING)
    migrated_db_session.add(document)
    await migrated_db_session.flush()
    task = _task(
        status=BackgroundTaskStatus.PENDING,
        created_at=stale,
        resource_id=document.id,
    )
    migrated_db_session.add(task)
    await migrated_db_session.flush()
    event = _outbox_event_for(task, document)
    migrated_db_session.add(event)
    await migrated_db_session.commit()

    reconciled = await fail_stale_pending_tasks(
        migrated_db_session,
        stale_after_seconds=3600,
    )

    assert reconciled == (task.id,)

    await migrated_db_session.refresh(task)
    assert task.status is BackgroundTaskStatus.FAILED
    await migrated_db_session.refresh(document)
    assert document.ingestion_status is IngestionStatus.FAILED
    await migrated_db_session.refresh(event)
    assert event.status is OutboxEventStatus.FAILED
    assert event.last_error == RECONCILED_OUTBOX_ERROR
    assert event.attempts == 0

    published: list[uuid.UUID] = []
    monkeypatch.setattr(
        outbox,
        "_publish_outbox_event",
        lambda candidate: published.append(candidate.id),
    )
    result = await outbox.dispatch_pending_outbox_events(migrated_db_session)

    assert published == []
    assert result.pending == 0
    await migrated_db_session.refresh(event)
    assert event.status is OutboxEventStatus.FAILED


async def test_fail_stale_pending_tasks_leaves_published_task_pending(
    migrated_db_session: AsyncSession,
) -> None:
    stale = datetime.now(UTC) - timedelta(hours=2)
    document = _document(status=IngestionStatus.PENDING)
    migrated_db_session.add(document)
    await migrated_db_session.flush()
    task = _task(
        status=BackgroundTaskStatus.PENDING,
        created_at=stale,
        resource_id=document.id,
    )
    migrated_db_session.add(task)
    await migrated_db_session.flush()
    event = _outbox_event_for(task, document)
    event.status = OutboxEventStatus.PUBLISHED
    event.published_at = datetime.now(UTC)
    event.attempts = 1
    migrated_db_session.add(event)
    await migrated_db_session.commit()

    reconciled = await fail_stale_pending_tasks(
        migrated_db_session,
        stale_after_seconds=3600,
    )

    assert reconciled == ()
    await migrated_db_session.refresh(task)
    assert task.status is BackgroundTaskStatus.PENDING
    await migrated_db_session.refresh(document)
    assert document.ingestion_status is IngestionStatus.PENDING
    await migrated_db_session.refresh(event)
    assert event.status is OutboxEventStatus.PUBLISHED


async def test_reconciliation_skips_task_when_dispatch_holds_outbox_lock(
    committed_migration_database,
) -> None:
    engine = create_async_engine(
        committed_migration_database.url,
        poolclass=NullPool,
    )
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    try:
        stale = datetime.now(UTC) - timedelta(hours=2)
        async with session_factory() as setup:
            document = _document(status=IngestionStatus.PENDING)
            setup.add(document)
            await setup.flush()
            task = _task(
                status=BackgroundTaskStatus.PENDING,
                created_at=stale,
                resource_id=document.id,
            )
            setup.add(task)
            await setup.flush()
            event = _outbox_event_for(task, document)
            setup.add(event)
            await setup.commit()
            document_id = document.id
            task_id = task.id
            event_id = event.id

        async with (
            session_factory() as dispatch_session,
            session_factory() as reconcile_session,
        ):
            claimed = (
                await dispatch_session.execute(
                    select(OutboxEvent)
                    .where(OutboxEvent.id == event_id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            ).scalar_one()

            reconciliation = asyncio.create_task(
                fail_stale_pending_tasks(
                    reconcile_session,
                    stale_after_seconds=3600,
                )
            )
            try:
                await asyncio.sleep(0.3)
                assert not reconciliation.done()

                claimed.status = OutboxEventStatus.PUBLISHED
                claimed.published_at = datetime.now(UTC)
                claimed.attempts += 1
                await dispatch_session.commit()

                reconciled = await asyncio.wait_for(reconciliation, timeout=10)
            finally:
                if not reconciliation.done():
                    reconciliation.cancel()
                    await asyncio.gather(
                        reconciliation,
                        return_exceptions=True,
                    )

        assert reconciled == ()

        async with session_factory() as verify:
            verified_task = await verify.get(BackgroundTask, task_id)
            verified_document = await verify.get(Document, document_id)
            verified_event = await verify.get(OutboxEvent, event_id)
            assert verified_task is not None
            assert verified_task.status is BackgroundTaskStatus.PENDING
            assert verified_document is not None
            assert verified_document.ingestion_status is IngestionStatus.PENDING
            assert verified_event is not None
            assert verified_event.status is OutboxEventStatus.PUBLISHED
    finally:
        await engine.dispose()


async def _seed_workflow_run(
    session: AsyncSession,
    *,
    status: WorkflowRunStatus,
) -> WorkflowRun:
    admin, _ = await seed_admin(session)
    _, customer, _ = await seed_customer(session)
    equipment = await seed_equipment(session, customer)
    complaint = await seed_complaint(session, customer, equipment=equipment)
    run = WorkflowRun(
        complaint_id=complaint.id,
        workflow_type=WorkflowRunType.DIAGNOSTIC_INVESTIGATION,
        requested_by_id=admin.id,
        status=status,
        current_step="investigating",
    )
    session.add(run)
    await session.flush()
    return run


async def _seed_workflow_task(
    session: AsyncSession,
    run: WorkflowRun,
    *,
    started_at: datetime,
    status: BackgroundTaskStatus = BackgroundTaskStatus.RUNNING,
) -> BackgroundTask:
    task = BackgroundTask(
        task_name="workflows.diagnostic_investigation",
        celery_task_id=str(uuid.uuid4()),
        status=status,
        resource_type="workflow_run",
        resource_id=run.id,
        attempts=1,
        started_at=started_at,
    )
    task.created_at = started_at
    session.add(task)
    await session.commit()
    return task


async def test_fail_stale_running_workflow_task_fails_task_and_run(
    migrated_db_session: AsyncSession,
) -> None:
    stale = datetime.now(UTC) - timedelta(hours=2)
    run = await _seed_workflow_run(
        migrated_db_session,
        status=WorkflowRunStatus.RUNNING,
    )
    task = await _seed_workflow_task(
        migrated_db_session,
        run,
        started_at=stale,
    )

    reconciled = await fail_stale_running_tasks(
        migrated_db_session,
        stale_after_seconds=3600,
    )

    assert reconciled == (task.id,)
    await migrated_db_session.refresh(task)
    await migrated_db_session.refresh(run)
    assert task.status is BackgroundTaskStatus.FAILED
    assert task.error_message == RECONCILED_RUNNING_TASK_ERROR
    assert task.finished_at is not None
    assert run.status is WorkflowRunStatus.FAILED
    assert run.current_step == "failed"
    assert run.error_message == RECONCILED_RUNNING_WORKFLOW_ERROR
    assert run.finished_at is not None


async def test_fail_stale_running_workflow_task_skips_active_claims(
    migrated_db_session: AsyncSession,
) -> None:
    run = await _seed_workflow_run(
        migrated_db_session,
        status=WorkflowRunStatus.RUNNING,
    )
    task = await _seed_workflow_task(
        migrated_db_session,
        run,
        started_at=datetime.now(UTC),
    )

    reconciled = await fail_stale_running_tasks(
        migrated_db_session,
        stale_after_seconds=1,
    )

    assert reconciled == ()
    await migrated_db_session.refresh(task)
    await migrated_db_session.refresh(run)
    assert task.status is BackgroundTaskStatus.RUNNING
    assert run.status is WorkflowRunStatus.RUNNING


async def test_fail_stale_running_workflow_task_reconciles_completed_run(
    migrated_db_session: AsyncSession,
) -> None:
    stale = datetime.now(UTC) - timedelta(hours=2)
    run = await _seed_workflow_run(
        migrated_db_session,
        status=WorkflowRunStatus.COMPLETED,
    )
    task = await _seed_workflow_task(
        migrated_db_session,
        run,
        started_at=stale,
    )

    reconciled = await fail_stale_running_tasks(
        migrated_db_session,
        stale_after_seconds=3600,
    )

    assert reconciled == (task.id,)
    await migrated_db_session.refresh(task)
    assert task.status is BackgroundTaskStatus.SUCCEEDED
    assert task.finished_at is not None
    assert task.error_message is None
