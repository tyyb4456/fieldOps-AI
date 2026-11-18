from __future__ import annotations

import pytest

from app.models.enums import ComplaintStatus, UserRole
from app.services.complaints.lifecycle import (
    ALLOWED_TRANSITIONS,
    LIFECYCLE_ERROR_HTTP_STATUS,
    READINESS_REQUIREMENTS,
    READINESS_SOURCE_STATUSES,
    TERMINAL_STATUSES,
    ComplaintLifecycleError,
    ComplaintStatusConflictError,
    DiagnosticNotReadyError,
    DiagnosticStaleError,
    EquipmentRequiredError,
    InvalidComplaintStatusTransitionError,
    InvalidLifecycleInputError,
    InvestigationAlreadyRunningError,
    LifecycleActor,
    LifecycleErrorCode,
    LifecycleEvent,
    LifecycleValidationError,
    PendingProposalConflictError,
    ReadinessMarker,
    ReadinessOperation,
    ReadinessProvenance,
    TerminalComplaintError,
    actor_from_user_role,
    available_transitions,
    classify_readiness_provenance,
    coerce_actor,
    coerce_status,
    evaluate_readiness_provenance,
    http_status_for_error,
    is_legacy_readiness_eligible,
    is_terminal,
    is_transition_allowed,
    required_transition_fields,
    validate_expected_status,
    validate_transition,
    validate_transition_fields,
)

CUSTOMER = LifecycleActor.CUSTOMER
TECHNICIAN = LifecycleActor.TECHNICIAN
ADMIN = LifecycleActor.ADMIN
SYSTEM = LifecycleActor.SYSTEM

RECEIVED = ComplaintStatus.RECEIVED
ANALYZING = ComplaintStatus.ANALYZING
AWAITING_CUSTOMER = ComplaintStatus.AWAITING_CUSTOMER
READY = ComplaintStatus.READY_FOR_WORK_ORDER
CONVERTED = ComplaintStatus.CONVERTED
ESCALATED = ComplaintStatus.ESCALATED
CLOSED = ComplaintStatus.CLOSED
CANCELLED = ComplaintStatus.CANCELLED

NON_TERMINAL_STATUSES = tuple(
    status for status in ComplaintStatus if status not in TERMINAL_STATUSES
)

EXPECTED_MATRIX: dict[
    ComplaintStatus, dict[ComplaintStatus, frozenset[LifecycleActor]]
] = {
    RECEIVED: {
        ANALYZING: frozenset({ADMIN}),
        AWAITING_CUSTOMER: frozenset({ADMIN}),
        ESCALATED: frozenset({ADMIN}),
        CLOSED: frozenset({ADMIN}),
        CANCELLED: frozenset({CUSTOMER, ADMIN}),
    },
    ANALYZING: {
        AWAITING_CUSTOMER: frozenset({ADMIN}),
        READY: frozenset({ADMIN}),
        ESCALATED: frozenset({ADMIN}),
        CLOSED: frozenset({ADMIN}),
        CANCELLED: frozenset({CUSTOMER, ADMIN}),
    },
    AWAITING_CUSTOMER: {
        ANALYZING: frozenset({CUSTOMER, ADMIN}),
        ESCALATED: frozenset({ADMIN}),
        CLOSED: frozenset({ADMIN}),
        CANCELLED: frozenset({CUSTOMER, ADMIN}),
    },
    READY: {
        CONVERTED: frozenset({SYSTEM}),
        ANALYZING: frozenset({ADMIN}),
        AWAITING_CUSTOMER: frozenset({ADMIN}),
        ESCALATED: frozenset({ADMIN}),
        CLOSED: frozenset({ADMIN}),
        CANCELLED: frozenset({CUSTOMER, ADMIN}),
    },
    ESCALATED: {
        ANALYZING: frozenset({ADMIN}),
        AWAITING_CUSTOMER: frozenset({ADMIN}),
        READY: frozenset({ADMIN}),
        CLOSED: frozenset({ADMIN}),
        CANCELLED: frozenset({ADMIN}),
    },
    CONVERTED: {},
    CLOSED: {},
    CANCELLED: {},
}


def _complete_marker(**overrides: object) -> ReadinessMarker:
    values: dict[str, object] = {
        "readiness_source": "lifecycle_v1",
        "diagnostic_workflow_run_id": "run-123",
        "diagnostic_context_fingerprint": "a" * 64,
        "diagnostic_context_fingerprint_version": 1,
        "diagnostic_evidence_revision": 7,
    }
    values.update(overrides)
    return ReadinessMarker(**values)


ALL_EDGES = [
    (source, target) for source in ComplaintStatus for target in ComplaintStatus
]


def test_transition_matrix_exactly_matches_approved_design() -> None:
    assert {
        source: dict(targets) for source, targets in ALLOWED_TRANSITIONS.items()
    } == EXPECTED_MATRIX


@pytest.mark.parametrize(
    ("source", "target", "actors"),
    [
        (source, target, actors)
        for source, targets in EXPECTED_MATRIX.items()
        for target, actors in targets.items()
    ],
)
def test_every_allowed_transition_validates_for_permitted_actor(
    source: ComplaintStatus,
    target: ComplaintStatus,
    actors: frozenset[LifecycleActor],
) -> None:
    for actor in actors:
        validate_transition(source, target, actor)
        assert is_transition_allowed(source, target, actor)


@pytest.mark.parametrize(("source", "target"), ALL_EDGES)
@pytest.mark.parametrize("actor", list(LifecycleActor))
def test_forbidden_transitions_are_rejected(
    source: ComplaintStatus,
    target: ComplaintStatus,
    actor: LifecycleActor,
) -> None:
    if source in TERMINAL_STATUSES:
        pytest.skip("Terminal sources are covered by terminal-state tests")

    allowed_actors = EXPECTED_MATRIX[source].get(target, frozenset())
    if actor in allowed_actors:
        return

    with pytest.raises(InvalidComplaintStatusTransitionError) as exc_info:
        validate_transition(source, target, actor)
    assert exc_info.value.code is LifecycleErrorCode.INVALID_STATUS_TRANSITION


def test_removed_awaiting_customer_to_ready_transition_is_forbidden() -> None:
    assert READY not in ALLOWED_TRANSITIONS[AWAITING_CUSTOMER]
    assert READINESS_SOURCE_STATUSES == frozenset({ANALYZING, ESCALATED})

    for actor in (CUSTOMER, TECHNICIAN, ADMIN, SYSTEM):
        with pytest.raises(InvalidComplaintStatusTransitionError):
            validate_transition(AWAITING_CUSTOMER, READY, actor)
        assert not is_transition_allowed(AWAITING_CUSTOMER, READY, actor)


def test_any_transition_to_received_is_forbidden() -> None:
    for source in NON_TERMINAL_STATUSES:
        if source == RECEIVED:
            continue
        with pytest.raises(InvalidComplaintStatusTransitionError):
            validate_transition(source, RECEIVED, ADMIN)


def test_manual_transition_to_converted_is_forbidden() -> None:
    for source in NON_TERMINAL_STATUSES:
        for actor in (CUSTOMER, TECHNICIAN, ADMIN):
            assert not is_transition_allowed(source, CONVERTED, actor)
            with pytest.raises(InvalidComplaintStatusTransitionError):
                validate_transition(source, CONVERTED, actor)

    validate_transition(READY, CONVERTED, SYSTEM)


@pytest.mark.parametrize(
    "source",
    [RECEIVED, ANALYZING, AWAITING_CUSTOMER, READY],
)
def test_customer_may_cancel_from_only_the_approved_states(
    source: ComplaintStatus,
) -> None:
    validate_transition(source, CANCELLED, CUSTOMER)
    assert is_transition_allowed(source, CANCELLED, CUSTOMER)


def test_customer_cannot_cancel_escalated_or_terminal_complaints() -> None:
    with pytest.raises(InvalidComplaintStatusTransitionError):
        validate_transition(ESCALATED, CANCELLED, CUSTOMER)

    for terminal in TERMINAL_STATUSES:
        with pytest.raises(TerminalComplaintError):
            validate_transition(terminal, CANCELLED, CUSTOMER)


def test_customer_may_reply_from_awaiting_customer_but_not_start_analysis() -> None:
    validate_transition(AWAITING_CUSTOMER, ANALYZING, CUSTOMER)
    with pytest.raises(InvalidComplaintStatusTransitionError):
        validate_transition(RECEIVED, ANALYZING, CUSTOMER)


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (ANALYZING, READY),
        (ESCALATED, READY),
        (ANALYZING, ESCALATED),
        (ANALYZING, CLOSED),
        (READY, CONVERTED),
        (READY, ANALYZING),
        (READY, AWAITING_CUSTOMER),
    ],
)
def test_customer_cannot_manage_lifecycle_states(
    source: ComplaintStatus,
    target: ComplaintStatus,
) -> None:
    with pytest.raises(InvalidComplaintStatusTransitionError):
        validate_transition(source, target, CUSTOMER)


def test_technicians_have_no_complaint_lifecycle_authority() -> None:
    for source in ComplaintStatus:
        assert available_transitions(source, TECHNICIAN) == ()
        for target in ComplaintStatus:
            assert not is_transition_allowed(source, target, TECHNICIAN)
            if source in TERMINAL_STATUSES:
                with pytest.raises(TerminalComplaintError):
                    validate_transition(source, target, TECHNICIAN)
            else:
                with pytest.raises(InvalidComplaintStatusTransitionError):
                    validate_transition(source, target, TECHNICIAN)


def test_admin_may_perform_every_admin_transition() -> None:
    for source, targets in EXPECTED_MATRIX.items():
        for target, actors in targets.items():
            if ADMIN in actors:
                validate_transition(source, target, ADMIN)
                assert is_transition_allowed(source, target, ADMIN)


def test_admin_cannot_write_converted_directly() -> None:
    with pytest.raises(InvalidComplaintStatusTransitionError):
        validate_transition(READY, CONVERTED, ADMIN)


def test_admin_cancellation_is_allowed_from_escalated() -> None:
    validate_transition(ESCALATED, CANCELLED, ADMIN)


def test_system_actor_only_writes_converted_from_ready() -> None:
    validate_transition(READY, CONVERTED, SYSTEM)
    assert available_transitions(READY, SYSTEM) == (CONVERTED,)

    for source, target in ALL_EDGES:
        if (source, target) == (READY, CONVERTED):
            continue
        if source in TERMINAL_STATUSES:
            with pytest.raises(TerminalComplaintError):
                validate_transition(source, target, SYSTEM)
        else:
            with pytest.raises(InvalidComplaintStatusTransitionError):
                validate_transition(source, target, SYSTEM)


@pytest.mark.parametrize("terminal", list(TERMINAL_STATUSES))
def test_terminal_states_reject_every_transition(
    terminal: ComplaintStatus,
) -> None:
    assert is_terminal(terminal)
    assert available_transitions(terminal, ADMIN) == ()

    for target in ComplaintStatus:
        if target == terminal:
            continue
        with pytest.raises(TerminalComplaintError):
            validate_transition(terminal, target, ADMIN)
        assert not is_transition_allowed(terminal, target, ADMIN)


def test_expected_status_mismatch_raises_conflict() -> None:
    with pytest.raises(ComplaintStatusConflictError) as exc_info:
        validate_transition(
            ANALYZING,
            ESCALATED,
            ADMIN,
            expected_status=RECEIVED,
        )

    error = exc_info.value
    assert error.code is LifecycleErrorCode.COMPLAINT_STATUS_CONFLICT
    assert error.expected_status is RECEIVED
    assert error.current_status is ANALYZING


def test_expected_status_mismatch_takes_precedence_over_terminal_state() -> None:
    with pytest.raises(ComplaintStatusConflictError):
        validate_transition(
            CONVERTED,
            ANALYZING,
            ADMIN,
            expected_status=READY,
        )


def test_matching_expected_status_allows_transition() -> None:
    validate_transition(
        ANALYZING,
        ESCALATED,
        ADMIN,
        expected_status=ANALYZING,
    )
    validate_expected_status(ANALYZING, ANALYZING)


def test_invalid_transition_inputs_are_rejected() -> None:
    with pytest.raises(InvalidLifecycleInputError):
        coerce_status(None)  # type: ignore[arg-type]
    with pytest.raises(InvalidLifecycleInputError):
        coerce_status("not_a_status")
    with pytest.raises(InvalidLifecycleInputError):
        coerce_actor(None)  # type: ignore[arg-type]
    with pytest.raises(InvalidLifecycleInputError):
        coerce_actor("not_an_actor")

    with pytest.raises(InvalidComplaintStatusTransitionError):
        validate_transition(ANALYZING, ANALYZING, ADMIN)
    with pytest.raises(InvalidComplaintStatusTransitionError):
        validate_transition(RECEIVED, RECEIVED, ADMIN)


def test_user_roles_and_string_values_are_normalized() -> None:
    assert coerce_actor(UserRole.ADMIN) is ADMIN
    assert coerce_actor("admin") is ADMIN
    assert coerce_status("analyzing") is ANALYZING
    assert actor_from_user_role(UserRole.CUSTOMER) is CUSTOMER
    validate_transition("analyzing", "escalated", "admin")


def test_available_transitions_depend_on_actor() -> None:
    assert available_transitions(RECEIVED, CUSTOMER) == (CANCELLED,)
    assert available_transitions(RECEIVED, ADMIN) == (
        ANALYZING,
        AWAITING_CUSTOMER,
        ESCALATED,
        CLOSED,
        CANCELLED,
    )
    assert READY not in available_transitions(AWAITING_CUSTOMER, ADMIN)


def test_conditional_transition_fields_are_declared() -> None:
    assert required_transition_fields(AWAITING_CUSTOMER) == frozenset({"reason"})
    assert required_transition_fields(ESCALATED) == frozenset({"reason"})
    assert required_transition_fields(CLOSED) == frozenset(
        {"resolution_code", "resolution_summary"}
    )
    assert required_transition_fields(READY) == frozenset()
    assert required_transition_fields(CANCELLED) == frozenset()


def test_conditional_transition_fields_are_validated() -> None:
    validate_transition_fields(
        AWAITING_CUSTOMER,
        {"reason": "Please provide the serial number."},
    )

    with pytest.raises(LifecycleValidationError) as exc_info:
        validate_transition_fields(AWAITING_CUSTOMER, {"reason": "   "})
    assert exc_info.value.missing_fields == ("reason",)

    with pytest.raises(LifecycleValidationError) as exc_info:
        validate_transition_fields(
            CLOSED,
            {"resolution_code": "no_fault_found"},
        )
    assert exc_info.value.missing_fields == ("resolution_summary",)


def test_lifecycle_event_vocabulary_fits_history_column() -> None:
    assert {event.value for event in LifecycleEvent} >= {
        "created",
        "updated",
        "cancelled",
        "converted",
        "investigation_requested",
        "clarification_requested",
        "customer_responded",
        "ready_for_work_order",
        "escalated",
        "closed",
        "reopened",
        "proposal_superseded",
    }
    assert all(len(event.value) <= 40 for event in LifecycleEvent)


def test_readiness_requirements_encode_the_no_bypass_product_rule() -> None:
    assert READINESS_REQUIREMENTS == type(READINESS_REQUIREMENTS)()
    assert READINESS_REQUIREMENTS.requires_equipment
    assert READINESS_REQUIREMENTS.requires_completed_diagnostic
    assert READINESS_REQUIREMENTS.requires_pre_conversion_phase
    assert READINESS_REQUIREMENTS.requires_diagnosed_outcome
    assert READINESS_REQUIREMENTS.requires_escalation_clear
    assert READINESS_REQUIREMENTS.requires_supported_fingerprint_version
    assert READINESS_REQUIREMENTS.requires_fingerprint_match
    assert READINESS_REQUIREMENTS.requires_no_existing_work_order
    assert not READINESS_REQUIREMENTS.allows_legacy_exception


def test_complete_lifecycle_marker_classifies_as_lifecycle() -> None:
    marker = _complete_marker()
    assert marker.is_lifecycle()
    assert marker.is_complete_lifecycle_provenance()
    assert (
        classify_readiness_provenance(
            marker,
            has_lifecycle_marker_anywhere=True,
            legacy_allowlisted=True,
            created_before_enforcement_cutoff=True,
        )
        is ReadinessProvenance.LIFECYCLE
    )


@pytest.mark.parametrize(
    "marker",
    [
        _complete_marker(diagnostic_workflow_run_id=None),
        _complete_marker(diagnostic_context_fingerprint=None),
        _complete_marker(diagnostic_context_fingerprint="abc"),
        _complete_marker(diagnostic_context_fingerprint_version=None),
        _complete_marker(diagnostic_context_fingerprint_version=2),
        _complete_marker(diagnostic_evidence_revision=None),
        _complete_marker(diagnostic_evidence_revision=-1),
        _complete_marker(diagnostic_evidence_revision=True),
    ],
)
def test_incomplete_lifecycle_marker_classifies_as_corrupt(
    marker: ReadinessMarker,
) -> None:
    assert (
        classify_readiness_provenance(
            marker,
            has_lifecycle_marker_anywhere=True,
            legacy_allowlisted=False,
            created_before_enforcement_cutoff=False,
        )
        is ReadinessProvenance.LIFECYCLE_CORRUPT
    )


def test_legacy_readiness_eligibility_predicate() -> None:
    assert is_legacy_readiness_eligible(
        has_lifecycle_marker_anywhere=False,
        legacy_allowlisted=True,
        created_before_enforcement_cutoff=True,
    )
    assert not is_legacy_readiness_eligible(
        has_lifecycle_marker_anywhere=True,
        legacy_allowlisted=True,
        created_before_enforcement_cutoff=True,
    )
    assert not is_legacy_readiness_eligible(
        has_lifecycle_marker_anywhere=False,
        legacy_allowlisted=False,
        created_before_enforcement_cutoff=True,
    )
    assert not is_legacy_readiness_eligible(
        has_lifecycle_marker_anywhere=False,
        legacy_allowlisted=True,
        created_before_enforcement_cutoff=False,
    )


def test_legacy_readiness_requires_allowlist_cutoff_and_no_lifecycle_marker() -> None:
    assert (
        classify_readiness_provenance(
            None,
            has_lifecycle_marker_anywhere=False,
            legacy_allowlisted=True,
            created_before_enforcement_cutoff=True,
        )
        is ReadinessProvenance.LEGACY_ELIGIBLE
    )
    assert (
        classify_readiness_provenance(
            None,
            has_lifecycle_marker_anywhere=False,
            legacy_allowlisted=False,
            created_before_enforcement_cutoff=True,
        )
        is ReadinessProvenance.NOT_ELIGIBLE
    )
    assert (
        classify_readiness_provenance(
            None,
            has_lifecycle_marker_anywhere=False,
            legacy_allowlisted=True,
            created_before_enforcement_cutoff=False,
        )
        is ReadinessProvenance.NOT_ELIGIBLE
    )
    assert (
        classify_readiness_provenance(
            None,
            has_lifecycle_marker_anywhere=True,
            legacy_allowlisted=True,
            created_before_enforcement_cutoff=True,
        )
        is ReadinessProvenance.NOT_ELIGIBLE
    )


def test_lifecycle_provenance_requires_diagnostic_revalidation_for_all_operations() -> (
    None
):
    for operation in ReadinessOperation:
        decision = evaluate_readiness_provenance(
            ReadinessProvenance.LIFECYCLE,
            operation,
        )
        assert decision.requires_diagnostic_revalidation
        assert not decision.uses_legacy_exception


def test_corrupt_lifecycle_provenance_is_stale_for_all_operations() -> None:
    for operation in ReadinessOperation:
        with pytest.raises(DiagnosticStaleError):
            evaluate_readiness_provenance(
                ReadinessProvenance.LIFECYCLE_CORRUPT,
                operation,
            )


def test_not_eligible_provenance_is_diagnostic_not_ready() -> None:
    for operation in ReadinessOperation:
        with pytest.raises(DiagnosticNotReadyError):
            evaluate_readiness_provenance(
                ReadinessProvenance.NOT_ELIGIBLE,
                operation,
            )


def test_legacy_provenance_is_not_usable_for_new_readiness_confirmation() -> None:
    with pytest.raises(DiagnosticNotReadyError):
        evaluate_readiness_provenance(
            ReadinessProvenance.LEGACY_ELIGIBLE,
            ReadinessOperation.READINESS_CONFIRMATION,
        )


@pytest.mark.parametrize(
    "operation",
    [
        ReadinessOperation.DIRECT_CONVERSION,
        ReadinessOperation.PROPOSAL_APPROVAL,
    ],
)
def test_legacy_provenance_is_allowed_only_for_conversion_and_approval(
    operation: ReadinessOperation,
) -> None:
    decision = evaluate_readiness_provenance(
        ReadinessProvenance.LEGACY_ELIGIBLE,
        operation,
    )
    assert not decision.requires_diagnostic_revalidation
    assert decision.uses_legacy_exception


def test_unknown_readiness_values_are_rejected() -> None:
    with pytest.raises(InvalidLifecycleInputError):
        evaluate_readiness_provenance("unknown", ReadinessOperation.DIRECT_CONVERSION)
    with pytest.raises(InvalidLifecycleInputError):
        evaluate_readiness_provenance(ReadinessProvenance.LIFECYCLE, "unknown")


@pytest.mark.parametrize(
    ("error", "expected_code", "expected_status"),
    [
        (
            ComplaintStatusConflictError(
                expected_status=RECEIVED,
                current_status=ANALYZING,
            ),
            LifecycleErrorCode.COMPLAINT_STATUS_CONFLICT,
            409,
        ),
        (
            InvalidComplaintStatusTransitionError(
                current_status=ANALYZING,
                target_status=RECEIVED,
                actor=ADMIN,
            ),
            LifecycleErrorCode.INVALID_STATUS_TRANSITION,
            409,
        ),
        (
            TerminalComplaintError(current_status=CLOSED),
            LifecycleErrorCode.TERMINAL_COMPLAINT,
            409,
        ),
        (
            EquipmentRequiredError(),
            LifecycleErrorCode.EQUIPMENT_REQUIRED,
            409,
        ),
        (
            DiagnosticNotReadyError(),
            LifecycleErrorCode.DIAGNOSTIC_NOT_READY,
            409,
        ),
        (
            DiagnosticStaleError(),
            LifecycleErrorCode.DIAGNOSTIC_STALE,
            409,
        ),
        (
            InvestigationAlreadyRunningError(),
            LifecycleErrorCode.INVESTIGATION_ALREADY_RUNNING,
            409,
        ),
        (
            PendingProposalConflictError(),
            LifecycleErrorCode.PENDING_PROPOSAL_CONFLICT,
            409,
        ),
        (
            LifecycleValidationError("missing reason"),
            LifecycleErrorCode.VALIDATION_ERROR,
            422,
        ),
    ],
)
def test_lifecycle_error_taxonomy_maps_to_documented_status(
    error: ComplaintLifecycleError,
    expected_code: LifecycleErrorCode,
    expected_status: int,
) -> None:
    assert error.code is expected_code
    assert LIFECYCLE_ERROR_HTTP_STATUS[expected_code] == expected_status
    assert http_status_for_error(error) == expected_status


def test_lifecycle_error_codes_are_unique_and_stable() -> None:
    assert {code.value for code in LifecycleErrorCode} == {
        "complaint_status_conflict",
        "invalid_status_transition",
        "terminal_complaint",
        "equipment_required",
        "diagnostic_not_ready",
        "diagnostic_stale",
        "investigation_already_running",
        "pending_proposal_conflict",
        "validation_error",
    }
