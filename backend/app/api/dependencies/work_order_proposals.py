from __future__ import annotations

from fastapi import Depends

from app.api.dependencies.diagnostics import get_diagnostic_service
from app.core.config import settings
from app.services.chat_model import get_chat_model
from app.services.diagnostics import DiagnosticService
from app.services.work_order_proposals import WorkOrderProposalService


def get_work_order_proposal_service(
    diagnostic_service: DiagnosticService = Depends(get_diagnostic_service),
) -> WorkOrderProposalService:
    """Construct the proposal service from application settings.

    The chat model factory is only resolved when a proposal is generated, and
    the diagnostic service is reused internally so a client can never supply
    diagnostic results.
    """

    return WorkOrderProposalService(
        diagnostic_service=diagnostic_service,
        chat_model_factory=get_chat_model,
        max_tool_calls=settings.work_order_proposal_max_tool_calls,
        max_model_calls=settings.work_order_proposal_max_model_calls,
        technician_limit=settings.work_order_proposal_max_technicians,
    )
