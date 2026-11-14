from __future__ import annotations

from app.services.diagnostics.diagnostics import (
    DiagnosticAgentUnavailableError,
    DiagnosticRetrievalUnavailableError,
)
from app.services.shared.authorization import AccessDeniedError
from app.services.shared.retry import (
    PermanentError,
    TransientError,
    is_transient_error,
)
from app.services.work_orders.work_order_proposals import (
    InvalidProposalStateError,
    ProposalAgentUnavailableError,
    ProposalAlreadyConvertedError,
    ProposalAlreadyPendingError,
    ProposalGenerationError,
    ProposalNotEligibleError,
    ProposalStaleError,
    ProposalTechnicianNotEligibleError,
)

GENERIC_WORKFLOW_ERROR = (
    "The workflow could not be completed. Try again or contact operations "
    "support."
)


class WorkflowExecutionError(Exception):
    """Base class for safe-to-persist workflow execution failures."""


class WorkflowTransientError(WorkflowExecutionError, TransientError):
    """A retryable infrastructure or provider failure."""


class WorkflowPermanentError(WorkflowExecutionError, PermanentError):
    """A terminal failure that must not be retried."""


class WorkflowOwnershipLostError(WorkflowExecutionError):
    """Another delivery or an operator now owns the workflow execution."""


class WorkflowExecutionBusyError(Exception):
    """Another delivery currently owns the workflow execution claim."""

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__(
            "Another worker currently owns this workflow execution."
        )
        self.retry_after_seconds = max(int(retry_after_seconds), 1)


_SAFE_MESSAGES: tuple[tuple[type[BaseException], str], ...] = (
    (AccessDeniedError, "Complaint not found"),
    (
        DiagnosticRetrievalUnavailableError,
        "Knowledge base search is unavailable.",
    ),
    (
        DiagnosticAgentUnavailableError,
        "The diagnostic agent is unavailable.",
    ),
    (
        ProposalAgentUnavailableError,
        "The work-order preparation agent is unavailable.",
    ),
    (
        ProposalGenerationError,
        "The work-order proposal did not pass validation.",
    ),
    (
        ProposalNotEligibleError,
        "Complaint is not eligible for work-order preparation.",
    ),
    (
        ProposalAlreadyPendingError,
        "A work order proposal is already pending review.",
    ),
    (
        ProposalAlreadyConvertedError,
        "A work order already exists for this complaint.",
    ),
    (
        ProposalStaleError,
        "The work-order proposal is stale; generate a new proposal.",
    ),
    (
        ProposalTechnicianNotEligibleError,
        "The selected technician is not eligible for assignment.",
    ),
    (
        InvalidProposalStateError,
        "The work-order proposal cannot be changed in its current state.",
    ),
)


def safe_workflow_error_message(exc: BaseException) -> str:
    if isinstance(exc, WorkflowExecutionError):
        message = str(exc).strip()
        if message:
            return message
    for exception_type, message in _SAFE_MESSAGES:
        if isinstance(exc, exception_type):
            return message
    return GENERIC_WORKFLOW_ERROR


def classify_workflow_error(exc: BaseException) -> WorkflowExecutionError:
    if isinstance(exc, WorkflowExecutionError):
        return exc
    message = safe_workflow_error_message(exc)
    if is_transient_error(exc):
        return WorkflowTransientError(message)
    return WorkflowPermanentError(message)


__all__ = [
    "GENERIC_WORKFLOW_ERROR",
    "WorkflowExecutionBusyError",
    "WorkflowExecutionError",
    "WorkflowOwnershipLostError",
    "WorkflowPermanentError",
    "WorkflowTransientError",
    "classify_workflow_error",
    "safe_workflow_error_message",
]
