from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from app.models.enums import ComplaintStatus, UserRole


class LifecycleActor(str, Enum):
    """Actor categories that may request a complaint lifecycle action."""

    CUSTOMER = "customer"
    TECHNICIAN = "technician"
    ADMIN = "admin"
    SYSTEM = "system"


def actor_from_user_role(role: UserRole) -> LifecycleActor:
    """Translate an application user role into a lifecycle actor."""

    try:
        return LifecycleActor(role.value)
    except (AttributeError, ValueError) as exc:  # pragma: no cover - defensive
        raise InvalidLifecycleInputError(f"Unsupported user role: {role!r}") from exc


class LifecycleErrorCode(str, Enum):
    """Stable error codes exposed by lifecycle policy and future routes."""

    COMPLAINT_STATUS_CONFLICT = "complaint_status_conflict"
    INVALID_STATUS_TRANSITION = "invalid_status_transition"
    TERMINAL_COMPLAINT = "terminal_complaint"
    EQUIPMENT_REQUIRED = "equipment_required"
    DIAGNOSTIC_NOT_READY = "diagnostic_not_ready"
    DIAGNOSTIC_STALE = "diagnostic_stale"
    INVESTIGATION_ALREADY_RUNNING = "investigation_already_running"
    PENDING_PROPOSAL_CONFLICT = "pending_proposal_conflict"
    VALIDATION_ERROR = "validation_error"


LIFECYCLE_ERROR_HTTP_STATUS: Mapping[LifecycleErrorCode, int] = {
    LifecycleErrorCode.COMPLAINT_STATUS_CONFLICT: 409,
    LifecycleErrorCode.INVALID_STATUS_TRANSITION: 409,
    LifecycleErrorCode.TERMINAL_COMPLAINT: 409,
    LifecycleErrorCode.EQUIPMENT_REQUIRED: 409,
    LifecycleErrorCode.DIAGNOSTIC_NOT_READY: 409,
    LifecycleErrorCode.DIAGNOSTIC_STALE: 409,
    LifecycleErrorCode.INVESTIGATION_ALREADY_RUNNING: 409,
    LifecycleErrorCode.PENDING_PROPOSAL_CONFLICT: 409,
    LifecycleErrorCode.VALIDATION_ERROR: 422,
}


class InvalidLifecycleInputError(ValueError):
    """Raised when a caller supplies a value outside the lifecycle vocabulary."""


class ComplaintLifecycleError(Exception):
    """Base class for deterministic lifecycle policy failures."""

    code: LifecycleErrorCode = LifecycleErrorCode.INVALID_STATUS_TRANSITION

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ComplaintStatusConflictError(ComplaintLifecycleError):
    """The caller's expected status no longer matches the current status."""

    code = LifecycleErrorCode.COMPLAINT_STATUS_CONFLICT

    def __init__(
        self,
        *,
        expected_status: ComplaintStatus,
        current_status: ComplaintStatus,
    ) -> None:
        self.expected_status = expected_status
        self.current_status = current_status
        super().__init__(
            "Complaint status changed: expected "
            f"{expected_status.value}, current {current_status.value}"
        )


class InvalidComplaintStatusTransitionError(ComplaintLifecycleError):
    """The transition matrix or actor policy rejects the pair."""

    code = LifecycleErrorCode.INVALID_STATUS_TRANSITION

    def __init__(
        self,
        *,
        current_status: ComplaintStatus,
        target_status: ComplaintStatus,
        actor: LifecycleActor | None = None,
    ) -> None:
        self.current_status = current_status
        self.target_status = target_status
        self.actor = actor
        actor_text = f" for actor {actor.value}" if actor is not None else ""
        super().__init__(
            "Complaint cannot move from "
            f"{current_status.value} to {target_status.value}{actor_text}"
        )


class TerminalComplaintError(ComplaintLifecycleError):
    """The complaint is in a terminal lifecycle state."""

    code = LifecycleErrorCode.TERMINAL_COMPLAINT

    def __init__(self, *, current_status: ComplaintStatus) -> None:
        self.current_status = current_status
        super().__init__(f"Complaint is terminal in status {current_status.value}")


class EquipmentRequiredError(ComplaintLifecycleError):
    """Readiness requires an equipment association."""

    code = LifecycleErrorCode.EQUIPMENT_REQUIRED

    def __init__(self, message: str = "Readiness requires equipment.") -> None:
        super().__init__(message)


class DiagnosticNotReadyError(ComplaintLifecycleError):
    """No qualifying, current diagnostic evidence supports the operation."""

    code = LifecycleErrorCode.DIAGNOSTIC_NOT_READY

    def __init__(
        self,
        message: str = "A qualifying diagnostic is required.",
    ) -> None:
        super().__init__(message)


class DiagnosticStaleError(ComplaintLifecycleError):
    """Diagnostic evidence no longer matches the current complaint context."""

    code = LifecycleErrorCode.DIAGNOSTIC_STALE

    def __init__(
        self,
        message: str = "Diagnostic evidence is stale.",
    ) -> None:
        super().__init__(message)


class InvestigationAlreadyRunningError(ComplaintLifecycleError):
    """A non-terminal diagnostic investigation already exists."""

    code = LifecycleErrorCode.INVESTIGATION_ALREADY_RUNNING

    def __init__(
        self,
        message: str = "An investigation is already running.",
    ) -> None:
        super().__init__(message)


class PendingProposalConflictError(ComplaintLifecycleError):
    """A pending proposal blocks the requested operation."""

    code = LifecycleErrorCode.PENDING_PROPOSAL_CONFLICT

    def __init__(
        self,
        message: str = "A pending proposal must be resolved first.",
    ) -> None:
        super().__init__(message)


class LifecycleValidationError(ComplaintLifecycleError):
    """Required request data for a transition is missing or invalid."""

    code = LifecycleErrorCode.VALIDATION_ERROR

    def __init__(
        self,
        message: str,
        *,
        missing_fields: tuple[str, ...] = (),
    ) -> None:
        self.missing_fields = missing_fields
        super().__init__(message)


def http_status_for_error(error: ComplaintLifecycleError) -> int:
    """Return the documented HTTP status for a lifecycle policy error."""

    return LIFECYCLE_ERROR_HTTP_STATUS[error.code]


def coerce_status(value: ComplaintStatus | str) -> ComplaintStatus:
    """Normalize a status value or fail with an explicit input error."""

    if isinstance(value, ComplaintStatus):
        return value
    if isinstance(value, str):
        try:
            return ComplaintStatus(value)
        except ValueError as exc:
            raise InvalidLifecycleInputError(
                f"Unknown complaint status: {value!r}"
            ) from exc
    raise InvalidLifecycleInputError(
        f"Complaint status must be a ComplaintStatus or string, got "
        f"{type(value).__name__}"
    )


def coerce_actor(value: LifecycleActor | UserRole | str) -> LifecycleActor:
    """Normalize an actor value or fail with an explicit input error."""

    if isinstance(value, LifecycleActor):
        return value
    if isinstance(value, UserRole):
        return actor_from_user_role(value)
    if isinstance(value, str):
        try:
            return LifecycleActor(value)
        except ValueError as exc:
            raise InvalidLifecycleInputError(
                f"Unknown lifecycle actor: {value!r}"
            ) from exc
    raise InvalidLifecycleInputError(
        f"Lifecycle actor must be a LifecycleActor or string, got "
        f"{type(value).__name__}"
    )


# The authoritative transition matrix from Step 4.13.0, Section F.1.
# Only the named actor categories may request each edge. `converted` is
# system-only because work-order creation is its sole writer.
ALLOWED_TRANSITIONS: Mapping[
    ComplaintStatus,
    Mapping[ComplaintStatus, frozenset[LifecycleActor]],
] = {
    ComplaintStatus.RECEIVED: {
        ComplaintStatus.ANALYZING: frozenset({LifecycleActor.ADMIN}),
        ComplaintStatus.AWAITING_CUSTOMER: frozenset({LifecycleActor.ADMIN}),
        ComplaintStatus.ESCALATED: frozenset({LifecycleActor.ADMIN}),
        ComplaintStatus.CLOSED: frozenset({LifecycleActor.ADMIN}),
        ComplaintStatus.CANCELLED: frozenset(
            {LifecycleActor.CUSTOMER, LifecycleActor.ADMIN}
        ),
    },
    ComplaintStatus.ANALYZING: {
        ComplaintStatus.AWAITING_CUSTOMER: frozenset({LifecycleActor.ADMIN}),
        ComplaintStatus.READY_FOR_WORK_ORDER: frozenset({LifecycleActor.ADMIN}),
        ComplaintStatus.ESCALATED: frozenset({LifecycleActor.ADMIN}),
        ComplaintStatus.CLOSED: frozenset({LifecycleActor.ADMIN}),
        ComplaintStatus.CANCELLED: frozenset(
            {LifecycleActor.CUSTOMER, LifecycleActor.ADMIN}
        ),
    },
    ComplaintStatus.AWAITING_CUSTOMER: {
        ComplaintStatus.ANALYZING: frozenset(
            {LifecycleActor.CUSTOMER, LifecycleActor.ADMIN}
        ),
        ComplaintStatus.ESCALATED: frozenset({LifecycleActor.ADMIN}),
        ComplaintStatus.CLOSED: frozenset({LifecycleActor.ADMIN}),
        ComplaintStatus.CANCELLED: frozenset(
            {LifecycleActor.CUSTOMER, LifecycleActor.ADMIN}
        ),
    },
    ComplaintStatus.READY_FOR_WORK_ORDER: {
        ComplaintStatus.CONVERTED: frozenset({LifecycleActor.SYSTEM}),
        ComplaintStatus.ANALYZING: frozenset({LifecycleActor.ADMIN}),
        ComplaintStatus.AWAITING_CUSTOMER: frozenset({LifecycleActor.ADMIN}),
        ComplaintStatus.ESCALATED: frozenset({LifecycleActor.ADMIN}),
        ComplaintStatus.CLOSED: frozenset({LifecycleActor.ADMIN}),
        ComplaintStatus.CANCELLED: frozenset(
            {LifecycleActor.CUSTOMER, LifecycleActor.ADMIN}
        ),
    },
    ComplaintStatus.ESCALATED: {
        ComplaintStatus.ANALYZING: frozenset({LifecycleActor.ADMIN}),
        ComplaintStatus.AWAITING_CUSTOMER: frozenset({LifecycleActor.ADMIN}),
        ComplaintStatus.READY_FOR_WORK_ORDER: frozenset({LifecycleActor.ADMIN}),
        ComplaintStatus.CLOSED: frozenset({LifecycleActor.ADMIN}),
        ComplaintStatus.CANCELLED: frozenset({LifecycleActor.ADMIN}),
    },
    ComplaintStatus.CONVERTED: {},
    ComplaintStatus.CLOSED: {},
    ComplaintStatus.CANCELLED: {},
}

TERMINAL_STATUSES = frozenset(
    {
        ComplaintStatus.CONVERTED,
        ComplaintStatus.CLOSED,
        ComplaintStatus.CANCELLED,
    }
)

# Readiness may be confirmed only from these sources. In particular this
# excludes awaiting_customer, whose readiness edge was removed in Revision 3.
READINESS_SOURCE_STATUSES = frozenset(
    {
        ComplaintStatus.ANALYZING,
        ComplaintStatus.ESCALATED,
    }
)

TRANSITION_REQUIRED_FIELDS: Mapping[ComplaintStatus, frozenset[str]] = {
    ComplaintStatus.AWAITING_CUSTOMER: frozenset({"reason"}),
    ComplaintStatus.ESCALATED: frozenset({"reason"}),
    ComplaintStatus.CLOSED: frozenset({"resolution_code", "resolution_summary"}),
}


class LifecycleEvent(str, Enum):
    """History event vocabulary from the approved lifecycle design."""

    CREATED = "created"
    UPDATED = "updated"
    CANCELLED = "cancelled"
    CONVERTED = "converted"
    INVESTIGATION_REQUESTED = "investigation_requested"
    INVESTIGATION_COMPLETED = "investigation_completed"
    CLARIFICATION_REQUESTED = "clarification_requested"
    CUSTOMER_RESPONDED = "customer_responded"
    READY_FOR_WORK_ORDER = "ready_for_work_order"
    ESCALATED = "escalated"
    CLOSED = "closed"
    REOPENED = "reopened"
    PROPOSAL_SUPERSEDED = "proposal_superseded"


READINESS_SOURCE_LIFECYCLE_V1 = "lifecycle_v1"
SUPPORTED_CONTEXT_FINGERPRINT_VERSIONS = frozenset({1})


def is_terminal(status: ComplaintStatus | str) -> bool:
    return coerce_status(status) in TERMINAL_STATUSES


def transition_actors(
    current_status: ComplaintStatus | str,
    target_status: ComplaintStatus | str,
) -> frozenset[LifecycleActor]:
    """Return the actors allowed on an edge, or an empty set if absent."""

    current = coerce_status(current_status)
    target = coerce_status(target_status)
    return ALLOWED_TRANSITIONS.get(current, {}).get(target, frozenset())


def is_transition_allowed(
    current_status: ComplaintStatus | str,
    target_status: ComplaintStatus | str,
    actor: LifecycleActor | UserRole | str,
) -> bool:
    current = coerce_status(current_status)
    target = coerce_status(target_status)
    normalized_actor = coerce_actor(actor)
    if current in TERMINAL_STATUSES:
        return False
    return normalized_actor in transition_actors(current, target)


def available_transitions(
    current_status: ComplaintStatus | str,
    actor: LifecycleActor | UserRole | str,
) -> tuple[ComplaintStatus, ...]:
    """List the targets the actor may request from the current status."""

    current = coerce_status(current_status)
    normalized_actor = coerce_actor(actor)
    if current in TERMINAL_STATUSES:
        return ()
    return tuple(
        target
        for target, actors in ALLOWED_TRANSITIONS[current].items()
        if normalized_actor in actors
    )


def validate_expected_status(
    current_status: ComplaintStatus | str,
    expected_status: ComplaintStatus | str | None,
) -> None:
    """Apply the optimistic concurrency contract for lifecycle requests."""

    current = coerce_status(current_status)
    if expected_status is None:
        return
    expected = coerce_status(expected_status)
    if expected != current:
        raise ComplaintStatusConflictError(
            expected_status=expected,
            current_status=current,
        )


def validate_transition(
    current_status: ComplaintStatus | str,
    target_status: ComplaintStatus | str,
    actor: LifecycleActor | UserRole | str,
    *,
    expected_status: ComplaintStatus | str | None = None,
) -> None:
    """Validate one lifecycle transition without touching persistence."""

    current = coerce_status(current_status)
    target = coerce_status(target_status)
    normalized_actor = coerce_actor(actor)

    validate_expected_status(current, expected_status)

    if current in TERMINAL_STATUSES:
        raise TerminalComplaintError(current_status=current)

    actors = ALLOWED_TRANSITIONS.get(current, {}).get(target)
    if target == current or actors is None:
        raise InvalidComplaintStatusTransitionError(
            current_status=current,
            target_status=target,
            actor=normalized_actor,
        )

    if normalized_actor not in actors:
        raise InvalidComplaintStatusTransitionError(
            current_status=current,
            target_status=target,
            actor=normalized_actor,
        )


def required_transition_fields(
    target_status: ComplaintStatus | str,
) -> frozenset[str]:
    """Return the request fields a target status requires."""

    return TRANSITION_REQUIRED_FIELDS.get(coerce_status(target_status), frozenset())


def validate_transition_fields(
    target_status: ComplaintStatus | str,
    fields: Mapping[str, object],
) -> None:
    """Validate conditional request fields without interpreting evidence."""

    target = coerce_status(target_status)
    required = required_transition_fields(target)
    missing = tuple(
        name for name in sorted(required) if not _has_required_value(fields.get(name))
    )
    if missing:
        raise LifecycleValidationError(
            f"Missing required fields for {target.value}: " + ", ".join(missing),
            missing_fields=missing,
        )


def _has_required_value(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


@dataclass(frozen=True)
class ReadinessMarker:
    """Server-owned readiness provenance copied from complaint history.

    Client-supplied fingerprints are never accepted as authority. A later
    service reads this marker from the latest `ready_for_work_order` history
    event under the complaint lock.
    """

    readiness_source: str | None = None
    diagnostic_workflow_run_id: str | None = None
    diagnostic_context_fingerprint: str | None = None
    diagnostic_context_fingerprint_version: int | None = None
    diagnostic_evidence_revision: int | None = None

    def is_lifecycle(self) -> bool:
        return self.readiness_source == READINESS_SOURCE_LIFECYCLE_V1

    def is_complete_lifecycle_provenance(self) -> bool:
        return (
            self.is_lifecycle()
            and bool(self.diagnostic_workflow_run_id)
            and _is_sha256_hex(self.diagnostic_context_fingerprint)
            and self.diagnostic_context_fingerprint_version
            in SUPPORTED_CONTEXT_FINGERPRINT_VERSIONS
            and isinstance(self.diagnostic_evidence_revision, int)
            and not isinstance(self.diagnostic_evidence_revision, bool)
            and self.diagnostic_evidence_revision >= 0
        )


class ReadinessProvenance(str, Enum):
    """Classification of the readiness record for the current ready state."""

    LIFECYCLE = "lifecycle"
    LIFECYCLE_CORRUPT = "lifecycle_corrupt"
    LEGACY_ELIGIBLE = "legacy_eligible"
    NOT_ELIGIBLE = "not_eligible"


class ReadinessOperation(str, Enum):
    READINESS_CONFIRMATION = "readiness_confirmation"
    DIRECT_CONVERSION = "direct_conversion"
    PROPOSAL_APPROVAL = "proposal_approval"


@dataclass(frozen=True)
class ReadinessDecision:
    """Pure policy outcome for a readiness operation.

    `requires_diagnostic_revalidation` means a later transactional service
    must revalidate the diagnostic fingerprint before writing anything.
    """

    provenance: ReadinessProvenance
    requires_diagnostic_revalidation: bool
    uses_legacy_exception: bool


@dataclass(frozen=True)
class ReadinessRequirements:
    """The no-bypass readiness gate that later steps must enforce."""

    requires_equipment: bool = True
    requires_completed_diagnostic: bool = True
    requires_pre_conversion_phase: bool = True
    requires_diagnosed_outcome: bool = True
    requires_escalation_clear: bool = True
    requires_supported_fingerprint_version: bool = True
    requires_fingerprint_match: bool = True
    requires_no_existing_work_order: bool = True
    allows_legacy_exception: bool = False


READINESS_REQUIREMENTS = ReadinessRequirements()


def is_legacy_readiness_eligible(
    *,
    has_lifecycle_marker_anywhere: bool,
    legacy_allowlisted: bool,
    created_before_enforcement_cutoff: bool,
) -> bool:
    """Network-free legacy eligibility predicate from the approved design.

    The caller resolves the allowlist and cutoff from deployment configuration
    at the service boundary; this function only applies the deterministic rule.
    """

    return (
        not has_lifecycle_marker_anywhere
        and legacy_allowlisted
        and created_before_enforcement_cutoff
    )


def classify_readiness_provenance(
    marker: ReadinessMarker | None,
    *,
    has_lifecycle_marker_anywhere: bool,
    legacy_allowlisted: bool,
    created_before_enforcement_cutoff: bool,
) -> ReadinessProvenance:
    """Classify readiness provenance without reading external state."""

    if marker is not None and marker.is_lifecycle():
        if marker.is_complete_lifecycle_provenance():
            return ReadinessProvenance.LIFECYCLE
        return ReadinessProvenance.LIFECYCLE_CORRUPT

    if has_lifecycle_marker_anywhere:
        return ReadinessProvenance.NOT_ELIGIBLE

    if is_legacy_readiness_eligible(
        has_lifecycle_marker_anywhere=has_lifecycle_marker_anywhere,
        legacy_allowlisted=legacy_allowlisted,
        created_before_enforcement_cutoff=created_before_enforcement_cutoff,
    ):
        return ReadinessProvenance.LEGACY_ELIGIBLE

    return ReadinessProvenance.NOT_ELIGIBLE


def evaluate_readiness_provenance(
    provenance: ReadinessProvenance | str,
    operation: ReadinessOperation | str,
) -> ReadinessDecision:
    """Map a provenance class to the operation's policy decision.

    This does not validate fingerprints, query workflow runs, or mutate any
    state. It only states whether a later service must perform revalidation or
    may use the audited legacy exception.
    """

    if isinstance(provenance, ReadinessProvenance):
        normalized_provenance = provenance
    else:
        try:
            normalized_provenance = ReadinessProvenance(provenance)
        except (TypeError, ValueError) as exc:
            raise InvalidLifecycleInputError(
                f"Unknown readiness provenance: {provenance!r}"
            ) from exc

    if isinstance(operation, ReadinessOperation):
        normalized_operation = operation
    else:
        try:
            normalized_operation = ReadinessOperation(operation)
        except (TypeError, ValueError) as exc:
            raise InvalidLifecycleInputError(
                f"Unknown readiness operation: {operation!r}"
            ) from exc

    if normalized_provenance is ReadinessProvenance.LIFECYCLE:
        return ReadinessDecision(
            provenance=normalized_provenance,
            requires_diagnostic_revalidation=True,
            uses_legacy_exception=False,
        )

    if normalized_provenance is ReadinessProvenance.LIFECYCLE_CORRUPT:
        raise DiagnosticStaleError("Lifecycle readiness record is missing or invalid.")

    if normalized_provenance is ReadinessProvenance.LEGACY_ELIGIBLE:
        if normalized_operation is ReadinessOperation.READINESS_CONFIRMATION:
            raise DiagnosticNotReadyError(
                "New readiness always requires a qualifying diagnostic."
            )
        return ReadinessDecision(
            provenance=normalized_provenance,
            requires_diagnostic_revalidation=False,
            uses_legacy_exception=True,
        )

    raise DiagnosticNotReadyError("Complaint has no eligible readiness provenance.")


def _is_sha256_hex(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    return all(character in "0123456789abcdefABCDEF" for character in value)


__all__ = [
    "ALLOWED_TRANSITIONS",
    "LIFECYCLE_ERROR_HTTP_STATUS",
    "READINESS_REQUIREMENTS",
    "READINESS_SOURCE_LIFECYCLE_V1",
    "READINESS_SOURCE_STATUSES",
    "SUPPORTED_CONTEXT_FINGERPRINT_VERSIONS",
    "TERMINAL_STATUSES",
    "TRANSITION_REQUIRED_FIELDS",
    "ComplaintLifecycleError",
    "ComplaintStatusConflictError",
    "DiagnosticNotReadyError",
    "DiagnosticStaleError",
    "EquipmentRequiredError",
    "InvalidComplaintStatusTransitionError",
    "InvalidLifecycleInputError",
    "InvestigationAlreadyRunningError",
    "LifecycleActor",
    "LifecycleErrorCode",
    "LifecycleEvent",
    "LifecycleValidationError",
    "PendingProposalConflictError",
    "ReadinessDecision",
    "ReadinessMarker",
    "ReadinessOperation",
    "ReadinessProvenance",
    "ReadinessRequirements",
    "TerminalComplaintError",
    "actor_from_user_role",
    "available_transitions",
    "classify_readiness_provenance",
    "coerce_actor",
    "coerce_status",
    "evaluate_readiness_provenance",
    "http_status_for_error",
    "is_legacy_readiness_eligible",
    "is_terminal",
    "is_transition_allowed",
    "required_transition_fields",
    "transition_actors",
    "validate_expected_status",
    "validate_transition",
    "validate_transition_fields",
]
