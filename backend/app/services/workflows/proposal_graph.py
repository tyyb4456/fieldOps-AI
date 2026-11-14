from __future__ import annotations

import uuid
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.diagnostics.diagnostics import (
    DiagnosticResult,
    DiagnosticService,
)
from app.services.rag.vector_index import VectorIndex
from app.services.work_orders.work_order_proposals import (
    WorkOrderProposalService,
)
from app.services.workflows.context import WorkflowGraphContext
from app.services.workflows.diagnostic_graph import (
    ProgressCallback,
    build_diagnostic_graph,
)


class ProposalState(TypedDict, total=False):
    complaint_id: str
    diagnosis: DiagnosticResult
    proposal_id: str


def build_proposal_graph(
    *,
    proposal_service: WorkOrderProposalService,
    diagnostic_service: DiagnosticService,
    session: AsyncSession,
    user: User,
    vector_index: VectorIndex,
    on_step: ProgressCallback | None = None,
    workflow_run_id: uuid.UUID | None = None,
) -> Any:
    """Build the complete work-order-preparation LangGraph workflow.

    The graph validates the complaint, composes the diagnostic graph, ranks
    technicians deterministically, runs the bounded preparation agent and
    persists the proposal in a short locked transaction.
    """

    context = WorkflowGraphContext(
        session=session,
        user=user,
        vector_index=vector_index,
    )

    async def _step(name: str) -> None:
        if on_step is not None:
            await on_step(name)

    async def validate_node(state: ProposalState) -> dict[str, Any]:
        await _step("validating_complaint")
        generation_context = (
            await proposal_service.validate_generation_context(
                session=session,
                user=user,
                complaint_id=uuid.UUID(state["complaint_id"]),
                workflow_run_id=workflow_run_id,
            )
        )
        context.generation_context = generation_context
        return {
            "complaint_id": str(generation_context.complaint.id),
        }

    async def diagnose_node(state: ProposalState) -> dict[str, Any]:
        await _step("diagnosing")
        diagnostic_graph = build_diagnostic_graph(
            service=diagnostic_service,
            session=session,
            user=user,
            vector_index=vector_index,
            on_step=None,
        )
        diagnostic_state = await diagnostic_graph.ainvoke(
            {
                "complaint_id": state["complaint_id"],
                "focus": None,
            }
        )
        diagnosis = diagnostic_state.get("diagnosis")
        if not isinstance(diagnosis, DiagnosticResult):
            raise TypeError("Diagnostic workflow did not return a result")
        context.diagnosis = diagnosis
        return {"diagnosis": diagnosis}

    async def rank_node(state: ProposalState) -> dict[str, Any]:
        await _step("ranking_technicians")
        generation_context = context.generation_context
        if generation_context is None:
            raise RuntimeError("Complaint context was not validated")
        planning = await proposal_service.rank_technicians(
            session=session,
            context=generation_context,
        )
        context.proposal_planning = planning
        return {}

    async def draft_node(state: ProposalState) -> dict[str, Any]:
        await _step("drafting_proposal")
        generation_context = context.generation_context
        planning = context.proposal_planning
        diagnosis = context.diagnosis
        if (
            generation_context is None
            or planning is None
            or diagnosis is None
        ):
            raise RuntimeError("Proposal preparation context is incomplete")
        preparation = await proposal_service.draft_preparation(
            context=generation_context,
            diagnosis=diagnosis,
            planning=planning,
        )
        context.proposal_preparation = preparation
        return {}

    async def persist_node(state: ProposalState) -> dict[str, Any]:
        await _step("persisting_proposal")
        generation_context = context.generation_context
        preparation = context.proposal_preparation
        diagnosis = context.diagnosis
        if (
            generation_context is None
            or preparation is None
            or diagnosis is None
        ):
            raise RuntimeError("Proposal persistence context is incomplete")
        proposal = await proposal_service.persist_prepared_proposal(
            session=session,
            user=user,
            context=generation_context,
            diagnosis=diagnosis,
            preparation=preparation,
            workflow_run_id=workflow_run_id,
        )
        context.proposal = proposal
        return {"proposal_id": str(proposal.id)}

    graph = StateGraph(ProposalState)
    graph.add_node("validate", validate_node)
    graph.add_node("diagnose", diagnose_node)
    graph.add_node("rank", rank_node)
    graph.add_node("draft", draft_node)
    graph.add_node("persist", persist_node)
    graph.add_edge(START, "validate")
    graph.add_edge("validate", "diagnose")
    graph.add_edge("diagnose", "rank")
    graph.add_edge("rank", "draft")
    graph.add_edge("draft", "persist")
    graph.add_edge("persist", END)
    return graph.compile()


__all__ = ["ProposalState", "build_proposal_graph"]
