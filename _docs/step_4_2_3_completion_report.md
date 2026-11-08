# Step 4.2.3 Completion Report

Date: 2026-11-08
Scope: harden the flaky complaint history-ordering concurrency test and re-verify the backend suite. No production defect was found, no production code was changed, no migration was touched, and no commit was created. Step 4.3 was not started.

## Status

Green. The targeted complaint test is stable and the full backend suite passes.

- `tests/test_complaints_api.py::test_patch_first_then_cancel_preserves_history_order`: 10/10 consecutive isolated runs passed.
- `tests/test_complaints_api.py`: 34 passed.
- `tests/test_complaints_api.py` + `tests/test_assignment_lifecycle.py`: 48 passed.
- Full backend suite (latest run): **319 passed, 12 warnings in 369.40s**.
- `python -m compileall -q app alembic tests`: exit 0.
- `git diff --check`: clean (CRLF notices only).

## Root cause

The old helper in `backend/tests/test_complaints_api.py` waited for the cancel request by running a broad query:

```sql
SELECT count(*) FROM pg_stat_activity
WHERE datname = current_database()
AND wait_event_type = 'Lock'
```

This is unreliable for two reasons:

1. It matches any lock wait in the database, including unrelated sessions.
2. It can run before the cancellation request has reached the `FOR UPDATE` statement, then time out even though the request is about to block. The task was also not inspected, so a request that failed or finished early looked like a lock timeout.

The production cancel path was inspected and is correct; the flake was purely test synchronization.

## Fix (test only)

`backend/tests/test_complaints_api.py` only:

- Added `from sqlalchemy.exc import DBAPIError`.
- Added `_assert_complaint_row_locked(...)`: a separate connection proves the editor transaction holds the row lock via `SELECT ... FOR UPDATE NOWAIT`, expecting SQLSTATE `55P03` (lock_not_available).
- Added `_wait_for_blocked_complaint_lock(session, task, *, editor_pid, timeout=10)`: waits for the specific cancel backend that is blocked by the editor backend (`editor_pid = ANY(pg_blocking_pids(a.pid))`) and is either running the complaint `FOR UPDATE` statement or holds a granted tuple lock on `complaints`. It fails immediately with task state if the task finishes, is cancelled, or raises.
- Updated the test to capture `editor_pid`, gate the request with an `asyncio.Event`, and use the two new helpers. All original assertions are unchanged.

No assertions were weakened, no PostgreSQL locking was mocked, and the timeout remained 10 seconds.

## Verification detail

Commands were run from `backend/` with `backend/.venv/Scripts/python.exe`.

- Isolated failing test: repeated 10 times, all passed.
- Complaint file: 34 passed, 3 deprecation warnings.
- Complaint + assignment concurrency files: 48 passed.
- Full suite: 319 passed, 12 warnings (all `StarletteDeprecationWarning: 'HTTP_422_UNPROCESSABLE_ENTITY' is deprecated` in `test_complaints_api.py`, `test_customers_api.py`, `test_equipment_api.py`).

One earlier full-suite run (`fullC`) reported `1 failed, 318 passed` in `tests/test_assignment_lifecycle.py::test_service_record_update_reloads_after_work_order_lock`. That test was not modified and is outside this step's scope. It did not reproduce in the most recent 70 targeted stress iterations or in the latest full-suite run above. If it recurs, the same class of fix applies to its `_wait_for_blocked_lock` helper (target the specific waiter via `pg_blocking_pids` and report task state on timeout).

## Notes and limitations

- `ruff` and `mypy` are not installed in the virtual environment; only `compileall` and `git diff --check` were available.
- No commit was created and no Step 4.3 work was started.
