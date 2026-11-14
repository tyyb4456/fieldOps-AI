from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.work_order_proposal import WorkOrderProposal
from app.services.diagnostics.diagnostics import (
    DiagnosticAgentRun,
    DiagnosticPreparation,
    DiagnosticResult,
)
from app.services.rag.vector_index import VectorIndex
from app.services.work_orders.work_order_proposals import (
    GenerationContext,
    ProposalPlanning,
    ProposalPreparation,
)


@dataclass
class WorkflowGraphContext:
    """Mutable execution context shared by nodes of one workflow run.

    This object is intentionally process-local. It is never placed on the
    Celery message or persisted; only stable identifiers leave the API.
    """

    session: AsyncSession
    user: User
    vector_index: VectorIndex
    focus: str | None = None
    diagnostic_preparation: DiagnosticPreparation | None = None
    diagnostic_run: DiagnosticAgentRun | None = None
    diagnosis: DiagnosticResult | None = None
    generation_context: GenerationContext | None = None
    proposal_planning: ProposalPlanning | None = None
    proposal_preparation: ProposalPreparation | None = None
    proposal: WorkOrderProposal | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


__all__ = ["WorkflowGraphContext"]
