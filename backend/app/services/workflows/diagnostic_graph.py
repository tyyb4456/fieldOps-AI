from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.diagnostics.diagnostics import DiagnosticResult, DiagnosticService
from app.services.rag.vector_index import VectorIndex
from app.services.workflows.context import WorkflowGraphContext

ProgressCallback = Callable[[str], Awaitable[None]]


class DiagnosticState(TypedDict, total=False):
    complaint_id: str
    focus: str | None
    diagnosis: DiagnosticResult


def build_diagnostic_graph(
    *,
    service: DiagnosticService,
    session: AsyncSession,
    user: User,
    vector_index: VectorIndex,
    on_step: ProgressCallback | None = None,
) -> Any:
    """Build the bounded diagnostic LangGraph workflow.

    One Celery job invokes this whole graph. The graph owns context loading,
    the read-only diagnostic agent and evidence finalization.
    """

    context = WorkflowGraphContext(
        session=session,
        user=user,
        vector_index=vector_index,
    )

    async def _step(name: str) -> None:
        if on_step is not None:
            await on_step(name)

    async def prepare_node(state: DiagnosticState) -> dict[str, Any]:
        await _step("loading_context")
        complaint_id = uuid.UUID(state["complaint_id"])
        preparation = await service.prepare(
            session=session,
            user=user,
            complaint_id=complaint_id,
        )
        context.diagnostic_preparation = preparation
        context.focus = state.get("focus")
        return {
            "complaint_id": str(preparation.complaint.id),
            "focus": context.focus,
        }

    async def investigate_node(state: DiagnosticState) -> dict[str, Any]:
        await _step("investigating")
        preparation = context.diagnostic_preparation
        if preparation is None:
            raise RuntimeError("Diagnostic preparation was not loaded")
        run = await service.run_agent(
            user=user,
            vector_index=vector_index,
            preparation=preparation,
            focus=state.get("focus"),
        )
        context.diagnostic_run = run
        return {}

    async def finalize_node(state: DiagnosticState) -> dict[str, Any]:
        await _step("finalizing_diagnosis")
        preparation = context.diagnostic_preparation
        run = context.diagnostic_run
        if preparation is None or run is None:
            raise RuntimeError("Diagnostic agent did not produce a result")
        result = service.finalize(
            run=run,
            preparation=preparation,
        )
        context.diagnosis = result
        return {"diagnosis": result}

    graph = StateGraph(DiagnosticState)
    graph.add_node("prepare", prepare_node)
    graph.add_node("investigate", investigate_node)
    graph.add_node("finalize", finalize_node)
    graph.add_edge(START, "prepare")
    graph.add_edge("prepare", "investigate")
    graph.add_edge("investigate", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile()


__all__ = ["DiagnosticState", "build_diagnostic_graph"]
