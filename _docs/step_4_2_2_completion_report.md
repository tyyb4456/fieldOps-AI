# Step 4.2.2 Remediation Completion Report

Date: 2026-11-07
Scope: assignment lifecycle, lock ordering, stale ORM identity, service-record reload, and integrity-error translation.
Status: fixes complete; targeted tests pass. Full suite is 318/319 because of one pre-existing, unrelated complaint-concurrency flake (details below). No commit was created and no Step 4.3 work was started.

## Findings and fixes

### F1 (HIGH): stale ORM identity after a locking read

A `SELECT ... FOR UPDATE` can return an existing identity-map instance without refreshing its attributes. A concurrent reassignment could withdraw an offer, yet acceptance/rejection would still see the cached `offered` status and make a contradictory decision.

Fix: every locking read that is followed by a lifecycle decision now uses SQLAlchemy `execution_options(populate_existing=True)`:

- `backend/app/services/assignments.py:89` (`_lock_work_order`)
- `backend/app/services/assignments.py:200` (active-assignment lock)
- `backend/app/services/authorization.py:173`, `:195`, `:217` (work-order, assignment and service-record scoped getters when `for_update=True`)
- `backend/app/services/service_records.py:50` (`_lock_work_order`)
- `backend/app/services/work_orders.py:328` (`_withdraw_active_assignments`)

Active-assignment rows are also locked in a deterministic order with `.order_by(TechnicianAssignment.id)`.

### F2 (MEDIUM): escalation/return-to-pool lifecycle

Policy: escalation is an administrative pause. Moving an `assigned`, `accepted` or `in_progress` work order to `escalated` preserves the assignment row for context, but the job cannot be advanced by the technician. Returning it to `awaiting_assignment`, or cancelling it, withdraws any active assignment in the same transaction.

Fix: `transition_work_order` now calls `_withdraw_active_assignments` for targets `AWAITING_ASSIGNMENT` and `CANCELLED` (`backend/app/services/work_orders.py:409`). Withdrawal failure rolls back the whole status transition, so the order stays `escalated` and the assignment stays active. Rejection and administrator withdrawal already returned jobs to the pool; the invariant is now enforced on every path.

Invariant: a work order in `awaiting_assignment` never has an `offered` or `accepted` assignment. Migration `0008_active_assignment_unique` adds the partial unique index `uq_technician_assignments_active_work_order` as the database backstop.

### F3 (LOW): stale service-record reload

`update_service_record` validates the resulting `findings`/`work_performed` combination. A stale identity-map copy could validate against values that a concurrent update had already replaced.

Fix: service-record updates lock the work order with `populate_existing=True` (`backend/app/services/service_records.py:50`) and operate on the refreshed record. The validation uses current committed values.

### F4 (LOW): uncaught `IntegrityError` became HTTP 500

The partial unique index is still the final safeguard. Expected violations of `uq_technician_assignments_active_work_order` are now translated to `409 assignment_conflict` with a generic message; other integrity errors are re-raised and remain 500s.

- Detection: `backend/app/services/assignments.py:72` (`is_active_assignment_conflict`), checking `constraint_name`, asyncpg `diag.constraint_name`, then a string fallback.
- Assignment routes: `backend/app/api/routes/assignments.py:43`, `:189`, `:196`, `:249`, `:289`, `:328`, `:367`.
- Work-order accept/reject routes: `backend/app/api/routes/work_orders.py:90`, `:306`, `:345`.

Work-order creation keeps its separate `IntegrityError` -> work-order conflict mapping (`backend/app/api/routes/work_orders.py:188`); it is not affected by the assignment helper.

## Lock ordering

All assignment mutations acquire locks in the same order:

1. `work_orders` row (`SELECT ... FOR UPDATE`)
2. active `technician_assignments` rows (ordered by `TechnicianAssignment.id`)

This applies to creation, reassignment, acceptance, rejection, withdrawal, cancellation, and escalation-return. Competing transactions serialize on the work-order row before touching assignments, so they cannot interleave contradictory states. The database index remains the backstop for any future path that bypasses the service.

## Regression tests

New file: `backend/tests/test_assignment_lifecycle.py` (14 tests).

Coverage:

- acceptance racing reassignment returns `InvalidAssignmentStateError`, with the old row `withdrawn` and the replacement `offered`
- rejection racing reassignment behaves the same way
- a withdrawn assignment cannot be accepted; the pool can be re-offered afterward
- a stale assignment instance refreshes after the work-order lock
- escalation preserves the assignment; returning to `awaiting_assignment` withdraws offered, accepted, and in-progress assignments
- invalid escalation transitions are rejected with `409 invalid_status_transition`
- a simulated withdrawal failure rolls back the return-to-pool transition
- a service-record update reloads after the work-order lock and sees the competing committed values
- stale service-record values raise `ServiceRecordStateError`
- `is_active_assignment_conflict` matches only the active-assignment index
- unrelated integrity errors are not misreported as conflicts
- an active-assignment integrity violation returns a generic `409 assignment_conflict` without SQL details

Concurrency tests use direct service calls in separate sessions with an `asyncio.Event` to signal that the competing operation has started, then wait on `pg_stat_activity` before releasing the lock. This avoids relying on API-request scheduling and removes the earlier flakiness.

## Verification

Commands were run from `backend/` with `backend/.venv`.

- `tests/test_assignment_lifecycle.py`: 14 passed; repeated twice; race tests stable across 10 consecutive runs.
- `tests/test_assignment_lifecycle.py tests/test_work_orders_api.py`: 27 passed.
- `test_work_orders_api.py test_complaints_api.py test_authorization.py test_migrations.py`: 78 passed.
- First six test files (including both assignment and complaint suites): 157 passed.
- Full suite: 318 passed, 1 failed.

The single full-suite failure is `tests/test_complaints_api.py::test_patch_first_then_cancel_preserves_history_order`. Its local `_wait_for_blocked_lock` helper times out after 10 seconds while waiting for the cancel request to block on the complaint row. It is unrelated to assignment code, passes 8/8 in isolation, and passes in the first-six-file subset. A diagnostic-instrumented full run (production code unchanged; only the test helper reported task state) passed 319/319; the instrumentation was reverted afterward. The unmodified helper failed in three consecutive full-suite runs, so the suite is not reliably green on this machine until that pre-existing helper is hardened (for example, event-based synchronization like the assignment concurrency tests, or a longer timeout that also reports a prematurely finished task).

No `ruff` or `mypy` is installed in the virtual environment. `python -m compileall` and `git diff --check` completed successfully (the latter only reports CRLF warnings).

## Migration and schema status

- Code head: `0008_active_assignment_unique` (partial unique index on active assignments).
- The migration refuses to upgrade if an existing work order already has multiple active assignments.
- Test databases are created per test and migrated to head.
- The persistent development database `fieldops` remains at `0005_profile_enrichment` and was not upgraded or mutated.
- The migration docstring's revision id was corrected to match the actual revision (`0008_active_assignment_unique`).

## Documentation

- `_docs/backend_engineering.md`: assignment and service-record API rules, lifecycle invariant, escalation policy, lock ordering, stale-identity protection, integrity-conflict translation.
- `_docs/database_integrity_conventions.md`: new section 7 on one active assignment per work order, the lifecycle invariant, lock ordering, stale ORM identity, and conflict translation.
- `_docs/database_design.md`: Table 9 note on the active-assignment invariant and backstop index.

## Limitations and follow-ups

- Harden the pre-existing complaint-concurrency helper so the full suite is deterministically green; this is unrelated to Step 4.2.2 but currently blocks a clean CI claim.
- Add a lint/typecheck step once `ruff`/`mypy` are available.
- No commit was made.
