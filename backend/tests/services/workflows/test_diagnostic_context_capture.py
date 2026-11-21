from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.background_task import BackgroundTask
from app.models.enums import (
    BackgroundTaskStatus,
    WorkflowRunStatus,
    WorkflowRunType,
)
from app.models.workflow_run import WorkflowRun
from app.services.diagnostics.diagnostics import DiagnosticPreparation
from app.services.diagnostics.readiness_context import (
    DIAGNOSTIC_CONTEXT_FINGERPRINT_FIELDS,
)
from app.services.workflows.errors import WorkflowOwnershipLostError
from app.services.workflows.executor import _capture_diagnostic_context
from tests.support import (
    seed_admin,
    seed_complaint,
    seed_customer,
    seed_equipment,
)


async def _seed_run(
    session: AsyncSession,
) -> tuple[WorkflowRun, DiagnosticPreparation]:
    admin, _ = await seed_admin(session)
    _, customer, _ = await seed_customer(session)
    equipment = await seed_equipment(session, customer)
    complaint = await seed_complaint(session, customer, equipment=equipment)
    run = WorkflowRun(
        complaint_id=complaint.id,
        workflow_type=WorkflowRunType.DIAGNOSTIC_INVESTIGATION,
        requested_by_id=admin.id,
        input_payload={"focus": None},
        status=WorkflowRunStatus.RUNNING,
        current_step="loading_context",
    )
    session.add(run)
    await session.commit()
    preparation = DiagnosticPreparation(
        complaint=complaint,
        equipment=equipment,
        missing_information=(),
    )
    return run, preparation


@pytest.mark.asyncio
async def test_capture_persists_versioned_readiness_fingerprint(
    migrated_db_session: AsyncSession,
) -> None:
    run, preparation = await _seed_run(migrated_db_session)

    await _capture_diagnostic_context(
        migrated_db_session,
        run,
        preparation,
        background_task_id=None,
        claimed_started_at=None,
    )
    await migrated_db_session.commit()

    await migrated_db_session.refresh(run)
    payload = run.input_payload
    assert payload["focus"] is None
    assert payload["context_fingerprint_version"] == 1
    assert payload["context_fingerprint_fields"] == list(
        DIAGNOSTIC_CONTEXT_FINGERPRINT_FIELDS
    )
    assert isinstance(payload["evidence_revision"], int)
    assert payload["context_captured_at"]
    assert len(payload["context_fingerprint"]) == 64


@pytest.mark.asyncio
async def test_capture_accepts_the_active_worker_claim(
    migrated_db_session: AsyncSession,
) -> None:
    run, preparation = await _seed_run(migrated_db_session)
    started_at = datetime.now(UTC)
    task = BackgroundTask(
        task_name="diagnostic_investigation",
        status=BackgroundTaskStatus.RUNNING,
        resource_type="workflow_run",
        resource_id=run.id,
        started_at=started_at,
    )
    migrated_db_session.add(task)
    await migrated_db_session.commit()

    await _capture_diagnostic_context(
        migrated_db_session,
        run,
        preparation,
        background_task_id=task.id,
        claimed_started_at=started_at,
    )
    await migrated_db_session.commit()

    await migrated_db_session.refresh(run)
    assert "context_fingerprint" in run.input_payload


@pytest.mark.asyncio
async def test_capture_does_not_write_after_claim_loss(
    migrated_db_session: AsyncSession,
) -> None:
    run, preparation = await _seed_run(migrated_db_session)
    run_id = run.id
    stale_claim = datetime.now(UTC)
    task = BackgroundTask(
        task_name="diagnostic_investigation",
        status=BackgroundTaskStatus.PENDING,
        resource_type="workflow_run",
        resource_id=run.id,
    )
    migrated_db_session.add(task)
    await migrated_db_session.commit()

    with pytest.raises(WorkflowOwnershipLostError):
        await _capture_diagnostic_context(
            migrated_db_session,
            run,
            preparation,
            background_task_id=task.id,
            claimed_started_at=stale_claim,
        )
    await migrated_db_session.rollback()

    stored = await migrated_db_session.get(WorkflowRun, run_id)
    assert stored is not None
    assert "context_fingerprint" not in stored.input_payload
