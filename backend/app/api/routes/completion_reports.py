from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import (
    get_current_user,
    require_operations_user,
)
from app.api.serializers import completion_report_response
from app.core.exceptions import AppError
from app.db.session import get_db_session
from app.models.enums import EvidenceStatus
from app.models.user import User
from app.schemas.completion_report import (
    CompletionReportCreate,
    CompletionReportListResponse,
    CompletionReportResponse,
    CompletionReportUpdate,
)
from app.services import completion_reports as completion_report_service
from app.services import work_orders as work_order_service
from app.services.completion_reports import (
    CompletionReportAssociationError,
    CompletionReportConflictError,
    CompletionReportPermissionError,
    CompletionReportStateError,
    is_completion_report_integrity_conflict,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Completion Reports"])


def _completion_report_conflict_error() -> AppError:
    return AppError(
        "A completion report already exists for this work order.",
        status_code=status.HTTP_409_CONFLICT,
        code="completion_report_conflict",
    )


def _invalid_completion_report_state_error() -> AppError:
    return AppError(
        "Completion report cannot be changed in the current state.",
        status_code=status.HTTP_409_CONFLICT,
        code="invalid_completion_report_state",
    )


def _invalid_completion_report_association_error() -> AppError:
    return AppError(
        "Service record does not belong to this work order.",
        status_code=status.HTTP_409_CONFLICT,
        code="invalid_completion_report_association",
    )


def _completion_report_forbidden_error() -> AppError:
    return AppError(
        "Only administrators can change completion verification fields.",
        status_code=status.HTTP_403_FORBIDDEN,
        code="forbidden",
    )


@router.get(
    "/completion-reports",
    response_model=CompletionReportListResponse,
    summary="List completion reports visible to the authenticated user",
)
@router.get(
    "/admin/completion-reports",
    response_model=CompletionReportListResponse,
    summary="Admin: list all completion reports",
)
async def list_completion_reports(
    work_order_id: uuid.UUID | None = Query(default=None),
    service_record_id: uuid.UUID | None = Query(default=None),
    evidence_status: EvidenceStatus | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CompletionReportListResponse:
    items, total = (
        await completion_report_service.list_completion_reports(
            session,
            current_user,
            work_order_id=work_order_id,
            service_record_id=service_record_id,
            evidence_status=evidence_status,
            limit=limit,
            offset=offset,
        )
    )
    return CompletionReportListResponse(
        items=[completion_report_response(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/work-orders/{work_order_id}/completion-reports",
    response_model=CompletionReportListResponse,
    summary="List completion reports for an accessible work order",
)
@router.get(
    "/admin/work-orders/{work_order_id}/completion-reports",
    response_model=CompletionReportListResponse,
    summary="Admin: list a work order's completion reports",
)
async def list_work_order_completion_reports(
    work_order_id: uuid.UUID,
    evidence_status: EvidenceStatus | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CompletionReportListResponse:
    await work_order_service.get_work_order(
        session,
        current_user,
        work_order_id,
    )
    items, total = (
        await completion_report_service.list_completion_reports(
            session,
            current_user,
            work_order_id=work_order_id,
            service_record_id=None,
            evidence_status=evidence_status,
            limit=limit,
            offset=offset,
        )
    )
    return CompletionReportListResponse(
        items=[completion_report_response(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/completion-reports/{completion_report_id}",
    response_model=CompletionReportResponse,
    summary="Read a completion report visible to the authenticated user",
)
@router.get(
    "/admin/completion-reports/{completion_report_id}",
    response_model=CompletionReportResponse,
    summary="Admin: read a completion report",
)
async def read_completion_report(
    completion_report_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CompletionReportResponse:
    completion_report = await completion_report_service.get_completion_report(
        session,
        current_user,
        completion_report_id,
    )
    return completion_report_response(completion_report)


@router.post(
    "/work-orders/{work_order_id}/completion-reports",
    response_model=CompletionReportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a completion report for an authorized work order",
)
@router.post(
    "/admin/work-orders/{work_order_id}/completion-reports",
    response_model=CompletionReportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Admin: submit a completion report",
    include_in_schema=False,
)
async def create_completion_report(
    work_order_id: uuid.UUID,
    payload: CompletionReportCreate,
    current_user: User = Depends(require_operations_user),
    session: AsyncSession = Depends(get_db_session),
) -> CompletionReportResponse:
    try:
        completion_report = (
            await completion_report_service.create_completion_report(
                session,
                user=current_user,
                work_order_id=work_order_id,
                data=payload,
            )
        )
        await session.commit()
    except CompletionReportStateError as exc:
        await session.rollback()
        raise _invalid_completion_report_state_error() from exc
    except CompletionReportAssociationError as exc:
        await session.rollback()
        raise _invalid_completion_report_association_error() from exc
    except CompletionReportConflictError as exc:
        await session.rollback()
        raise _completion_report_conflict_error() from exc
    except IntegrityError as exc:
        await session.rollback()
        if not is_completion_report_integrity_conflict(exc):
            raise
        raise _completion_report_conflict_error() from exc

    await session.refresh(completion_report)
    logger.info(
        "Completion report created",
        extra={
            "event": "completion_report_created",
            "actor_id": str(current_user.id),
            "work_order_id": str(completion_report.work_order_id),
            "service_record_id": str(completion_report.service_record_id),
            "completion_report_id": str(completion_report.id),
        },
    )
    return completion_report_response(completion_report)


@router.patch(
    "/completion-reports/{completion_report_id}",
    response_model=CompletionReportResponse,
    summary="Update a completion report within its permitted lifecycle",
)
@router.patch(
    "/admin/completion-reports/{completion_report_id}",
    response_model=CompletionReportResponse,
    summary="Admin: update a completion report",
    include_in_schema=False,
)
async def update_completion_report(
    completion_report_id: uuid.UUID,
    payload: CompletionReportUpdate,
    current_user: User = Depends(require_operations_user),
    session: AsyncSession = Depends(get_db_session),
) -> CompletionReportResponse:
    try:
        completion_report = (
            await completion_report_service.update_completion_report(
                session,
                user=current_user,
                completion_report_id=completion_report_id,
                data=payload,
            )
        )
        await session.commit()
    except CompletionReportStateError as exc:
        await session.rollback()
        raise _invalid_completion_report_state_error() from exc
    except CompletionReportPermissionError as exc:
        await session.rollback()
        raise _completion_report_forbidden_error() from exc

    await session.refresh(completion_report)
    logger.info(
        "Completion report updated",
        extra={
            "event": "completion_report_updated",
            "actor_id": str(current_user.id),
            "work_order_id": str(completion_report.work_order_id),
            "completion_report_id": str(completion_report.id),
            "evidence_status": completion_report.evidence_status.value,
        },
    )
    return completion_report_response(completion_report)
