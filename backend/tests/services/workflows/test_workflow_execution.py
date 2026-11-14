from __future__ import annotations

from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.background_task import BackgroundTask
from app.models.complaint import Complaint
from app.models.enums import (
    BackgroundTaskStatus,
    OutboxEventStatus,
    WorkflowRunStatus,
    WorkflowRunType,
)
from app.models.outbox_event import OutboxEvent
from app.models.workflow_run import WorkflowRun
from app.services.diagnostics.diagnostics import (
    DiagnosticAgentUnavailableError,
    DiagnosticRetrievalUnavailableError,
)
from app.services.tasks.execution import (
    DIAGNOSTIC_INVESTIGATION_TASK_NAME,
)
from app.services.work_orders.work_order_proposals import (
    ProposalAlreadyPendingError,
    ProposalGenerationError,
)
from app.services.workflows.errors import (
    GENERIC_WORKFLOW_ERROR,
    WorkflowPermanentError,
    WorkflowTransientError,
    classify_workflow_error,
    safe_workflow_error_message,
)
from app.services.workflows.executor import execute_workflow
from app.services.workflows.scheduling import (
    schedule_diagnostic_investigation,
)
from tests.support import (
    seed_admin,
    seed_complaint,
    seed_customer,
    seed_equipment,
)


async def _seed_complaint(session: AsyncSession) -> Complaint:
    _, customer, _ = await seed_customer(session)
    equipment = await seed_equipment(session, customer)
    return await seed_complaint(session, customer, equipment=equipment)


@pytest.mark.asyncio
async def test_schedule_diagnostic_investigation_persists_ids_only(
    migrated_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin, _ = await seed_admin(migrated_db_session)
    complaint = await _seed_complaint(migrated_db_session)
    monkeypatch.setattr(settings, "celery_task_always_eager", False)

    pending = await schedule_diagnostic_investigation(
        migrated_db_session,
        user=admin,
        complaint_id=complaint.id,
        focus="  Check the DC input fuse.  ",
    )

    run = pending.workflow_run
    assert run.status is WorkflowRunStatus.RUNNING
    assert run.current_step == "queued"
    assert run.workflow_type is WorkflowRunType.DIAGNOSTIC_INVESTIGATION
    assert run.requested_by_id == admin.id
    assert run.input_payload == {"focus": "Check the DC input fuse."}

    task = await migrated_db_session.get(
        BackgroundTask,
        pending.background_task_id,
    )
    assert task is not None
    assert task.status is BackgroundTaskStatus.PENDING
    assert task.resource_type == "workflow_run"
    assert task.resource_id == run.id

    event = await migrated_db_session.get(
        OutboxEvent,
        pending.outbox_event_id,
    )
    assert event is not None
    assert event.event_type == DIAGNOSTIC_INVESTIGATION_TASK_NAME
    assert event.status is OutboxEventStatus.PENDING
    assert event.payload["workflow_run_id"] == str(run.id)
    assert event.payload["background_task_id"] == str(task.id)
    assert event.payload["args"] == [str(run.id), str(task.id)]
    assert "focus" not in event.payload
    assert "Check the DC input fuse." not in str(event.payload)


@pytest.mark.asyncio
async def test_execute_workflow_skips_terminal_runs(
    migrated_db_session: AsyncSession,
) -> None:
    complaint = await _seed_complaint(migrated_db_session)
    run = WorkflowRun(
        complaint_id=complaint.id,
        workflow_type=WorkflowRunType.DIAGNOSTIC_INVESTIGATION,
        status=WorkflowRunStatus.COMPLETED,
        current_step="completed",
    )
    migrated_db_session.add(run)
    await migrated_db_session.commit()

    result = await execute_workflow(
        migrated_db_session,
        workflow_run_id=run.id,
        vector_index=cast(Any, None),
    )

    assert result.id == run.id
    assert result.status is WorkflowRunStatus.COMPLETED


def test_workflow_error_messages_never_leak_provider_details() -> None:
    assert (
        safe_workflow_error_message(
            DiagnosticRetrievalUnavailableError("store down")
        )
        == "Knowledge base search is unavailable."
    )
    assert (
        safe_workflow_error_message(
            DiagnosticAgentUnavailableError("sk-secret-123 rejected")
        )
        == "The diagnostic agent is unavailable."
    )
    assert (
        safe_workflow_error_message(
            ProposalAlreadyPendingError("duplicate proposal")
        )
        == "A work order proposal is already pending review."
    )

    generic = safe_workflow_error_message(
        RuntimeError("postgres password is swordfish")
    )
    assert generic == GENERIC_WORKFLOW_ERROR
    assert "swordfish" not in generic

    classified = WorkflowPermanentError(
        "The diagnostic agent is unavailable."
    )
    assert (
        safe_workflow_error_message(classified)
        == "The diagnostic agent is unavailable."
    )


def test_classify_workflow_error_separates_transient_and_permanent() -> None:
    transient = classify_workflow_error(TimeoutError("provider timeout"))
    assert isinstance(transient, WorkflowTransientError)

    permanent = classify_workflow_error(
        ProposalGenerationError("invalid agent output")
    )
    assert isinstance(permanent, WorkflowPermanentError)
    assert not isinstance(permanent, WorkflowTransientError)
