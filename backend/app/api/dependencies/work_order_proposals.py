from __future__ import annotations

from fastapi import Depends

from app.api.dependencies.diagnostics import get_diagnostic_service
from app.services.diagnostics.diagnostics import DiagnosticService
from app.services.work_orders.work_order_proposals import (
    WorkOrderProposalService,
)
from app.services.workflows.factories import (
    build_work_order_proposal_service,
)


def get_work_order_proposal_service(
    diagnostic_service: DiagnosticService = Depends(get_diagnostic_service),
) -> WorkOrderProposalService:
    """Construct the proposal service from application settings.

    The chat model factory is only resolved when a proposal is generated, and
    the diagnostic service is reused internally so a client can never supply
    diagnostic results.
    """

    return build_work_order_proposal_service(
        diagnostic_service=diagnostic_service,
    )
