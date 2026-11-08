# Step 4.3 Completion Report

## Scope

Step 4.3 adds the completion-report, document-metadata, and workflow-run
backend surfaces on top of the Step 4.2 work-order lifecycle. It is limited to
the REST API, service layer, persistence constraints, migration and tests. It
does not implement AI orchestration, RAG ingestion, binary document storage, or
frontend work.

## Delivered

### Completion reports

- `POST /api/v1/work-orders/{work_order_id}/completion-reports`
- `GET /api/v1/completion-reports`
- `GET /api/v1/work-orders/{work_order_id}/completion-reports`
- `GET /api/v1/completion-reports/{completion_report_id}`
- `PATCH /api/v1/completion-reports/{completion_report_id}`

Rules enforced:

- One completion report per work order (service check plus database unique
  constraint).
- The associated service record must belong to the same work order through a
  composite foreign key into `service_records(id, work_order_id)`.
- The service record must document work performed.
- Reports can only be created while the work order is accepted, in progress,
  awaiting parts, or pending verification.
- Technicians must hold an accepted assignment on the work order and own the
  associated service record.
- Evidence transitions:
  - `pending -> verified | rejected`
  - `rejected -> pending | verified`
  - `verified` is immutable.
- Only administrators may change evidence status and verification notes.
  Technicians may edit the summary while the report is pending.
- Verified reports receive `verified_at`; rejecting or reopening clears it.

### Documents

Admin-only metadata endpoints:

- `GET/POST /api/v1/admin/documents`
- `GET/PATCH/DELETE /api/v1/admin/documents/{document_id}`
- `GET /api/v1/admin/documents/{document_id}/chunks`

New documents are always created inactive. Deletion cascades to stored
document chunks. No upload endpoint or binary storage is introduced; metadata
references an externally managed `file_path`.

### Workflow runs

Admin-only lifecycle endpoints:

- `GET/POST /api/v1/admin/complaints/{complaint_id}/workflow-runs`
- `GET /api/v1/admin/workflow-runs`
- `GET /api/v1/admin/workflow-runs/{workflow_run_id}`
- `POST /api/v1/admin/workflow-runs/{workflow_run_id}/status`

Lifecycle rules:

- New runs start as `running`.
- `running -> paused | completed | failed`
- `paused -> running | completed | failed`
- `completed` and `failed` are terminal.
- Terminal transitions set `finished_at`; reopening clears it.
- `error_message` is only accepted when the target status is `failed` and is
  cleared for non-failed transitions.
- Repeating the current status is rejected.

### Database

Migration `0009_completion_report_link` (revises
`0008_active_assignment_unique`):

- Adds nullable `completion_reports.service_record_id`.
- Adds `uq_service_records_id_work_order_id`.
- Adds `uq_completion_reports_work_order_id`.
- Adds `fk_completion_reports_service_record_work_order` with
  `ON DELETE RESTRICT`.
- Replaces the legacy non-unique work-order index.
- Aborts upgrade if duplicate reports already exist for one work order.
- Provides a full downgrade path.

## Tests

Added:

- `tests/test_completion_reports_api.py` (16 tests)
- `tests/test_documents_api.py` (8 tests)
- `tests/test_workflow_runs_api.py` (8 tests)
- Two Step 4.3 migration tests and updated constraint expectations in
  `tests/test_migrations.py`
- Updated relationship/constraint expectations in `tests/test_models.py` and
  `tests/test_model_integrity.py`

Coverage includes authentication, role isolation, tenant/technician scoping,
one-report-per-work-order conflicts, cross-work-order service-record
associations, immutability after verification, document activation/filtering,
chunk ordering and cascade deletion, workflow transitions, terminal protection,
error-message validation, pagination, and migration upgrade/downgrade guards.

## Verification

- Full suite: `353 passed` (previous baseline: 319).
- Migration suite: `16 passed`.
- `python -m compileall -q app tests alembic`: passed.
- `git diff --check`: clean (only CRLF normalization warnings).
- Alembic drift check is exercised by
  `test_alembic_check_reports_no_schema_drift` and passed.

## Known limitations

- Document binary content, upload/download, checksum validation, and chunk
  generation/ingestion are not implemented. The API manages metadata and
  exposes existing chunks only.
- AI orchestration, agent execution, and RAG retrieval are intentionally out of
  scope.
- No commits were created as part of this step.
