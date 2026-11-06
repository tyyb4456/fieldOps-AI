# FieldOps AI — Database Integrity Conventions

This note records database conventions that the application code must respect. It complements `database_design.md`; it does not replace it.

## 1. `updated_at` is maintained by the SQLAlchemy ORM

`complaints.updated_at` and `work_orders.updated_at` are updated by SQLAlchemy's `onupdate=func.now()` rule in `app/db/base.py`.

- Application writes must go through the SQLAlchemy ORM so `updated_at` is maintained.
- Direct SQL updates, bulk updates and scripts that bypass the ORM must set `updated_at` explicitly, for example `updated_at = now()`.
- No database trigger is used in the current architecture. A trigger should be added only if a concrete non-ORM write path makes it necessary.

This convention is intentional: the backend owns business writes, and the ORM is the expected write path.

## 2. Step 3 role/profile invariant

Authentication and RBAC are not implemented in Step 2.2. The future user/profile service must enforce the following invariant transactionally:

- A user with role `customer` must have exactly one `Customer` profile.
- A user with role `technician` must have exactly one `Technician` profile.
- A user with role `admin` must not have an operational profile unless the product explicitly permits it.
- A user must never have both a `Customer` and a `Technician` profile.
- Role changes must handle existing profiles atomically, removing or creating the appropriate profile within the same transaction.

This invariant is currently application-level. The database unique constraints on `customers.user_id` and `technicians.user_id` only prevent duplicate profiles of the same type; they do not enforce role/profile consistency. The future service must validate the user's role and profile together, and tests must cover mismatched roles, dual profiles and role changes. Database triggers are not required unless a concrete direct-write requirement appears.

## 3. Document version and activation rules

- Document version uniqueness is enforced with PostgreSQL `NULLS NOT DISTINCT`, so identical manufacturer, model, document name and `NULL` version cannot be duplicated. Different non-NULL versions remain allowed.
- New documents are inactive by default (`is_active = false`). They become retrievable only after an explicit approval step. The Step 2.2 default change did not deactivate existing document rows.
- PostgreSQL 15 or newer is required for the `NULLS NOT DISTINCT` constraint.

## 4. Complaint history is append-only and ordered by sequence

- `complaint_history` records `created`, `updated` and `cancelled` events. The complaint service inserts rows in the same transaction as the complaint mutation.
- Each row has a non-null `sequence_number`, unique per complaint via `UNIQUE (complaint_id, sequence_number)`. History reads and relationships order by `sequence_number`, not by `id` or `created_at`.
- The sequence is allocated by the complaint service as `MAX(sequence_number) + 1` for that complaint *while holding the complaint row lock* (`SELECT ... FOR UPDATE`). Every history-writing path acquires that lock first: the HTTP routes load the complaint with `FOR UPDATE`, and the service helpers also refresh/lock the complaint so internal callers cannot bypass serialization. The `MAX + 1` read is therefore safe because concurrent writers for the same complaint are serialized until commit.
- The complaint row lock is what makes the allocation transactionally consistent: two transactions can never observe the same maximum and insert the same `(complaint_id, sequence_number)`. If a caller ignores the lock, the unique constraint rejects the duplicate rather than silently corrupting the order.
- `created_at` uses PostgreSQL `now()`, which is the transaction start time, not the instant the event occurred. It must not be used to order events. Two transactions may start in one order, serialize on the complaint row lock in another, and commit in a third; `sequence_number` captures the committed order.
- History rows are never updated or deleted through the application. The ORM model has only `created_at`, no `updated_at`, and there is no write endpoint for history.
- `changed_fields` stores `{"from": ..., "to": ...}` entries for every changed complaint field. This preserves the original customer wording after an edit and makes field-level audit possible.
- `complaint_history.complaint_id` uses `ON DELETE RESTRICT`, so a complaint with history cannot be silently removed.

### Historical coverage limitation

- History tracking began with migration `0006_complaint_lifecycle`. Complaints that existed before it have no `created` event and no reconstructed `updated`/`cancelled` events. Migration `0006` only converted their stored status (`closed` to `cancelled`); it did not create audit rows.
- Migration `0007_complaint_history_sequence` backfills `sequence_number` for existing history rows using `ROW_NUMBER()` partitioned by `complaint_id` and ordered by `(created_at, id)`. This establishes a deterministic ordering of rows that exist; it cannot recover missing events or the original real-world order.
- Do not describe `created_at` alone as guaranteeing the actual order of changes. Use `sequence_number`, and state the pre-0006 coverage gap when presenting history.

## 5. Complaint cancellation uses a distinct status

- Customer cancellation transitions an eligible complaint to `cancelled`, not `closed`.
- `closed` remains available for a future internal closure process. Keeping the statuses separate prevents historical cancellation data from being confused with internal case closure.
- The `0006_complaint_lifecycle` migration added `cancelled` to the `complaints.status` check constraint and backfilled existing `closed` rows because the cancellation endpoint was the only code path that produced `closed`.
- Complaint updates and cancellations lock the complaint row (`SELECT ... FOR UPDATE`) before checking editability or transitioning status, preventing a PATCH from committing after a concurrent cancellation.

### Downgrade is destructive and guarded

Dropping below `0007_complaint_history_sequence` is **not fully reversible**:

- `0007` refuses to downgrade while `complaint_history` contains any row, because dropping `sequence_number` would destroy the deterministic order.
- Continuing below `0006_complaint_lifecycle` drops the entire `complaint_history` table and converts `cancelled` back to `closed`, so the cancellation/closure distinction is lost.
- The guard in `0007` runs first for any downgrade from head, so a non-empty history stream cannot be silently discarded by `alembic downgrade`.

**Required archival procedure before downgrade:**

1. Create and verify a backup of the database, or at minimum of `complaint_history`, for example `COPY (SELECT * FROM complaint_history ORDER BY complaint_id, sequence_number) TO '/path/complaint_history.csv' WITH CSV HEADER`, or `pg_dump --table=complaint_history`.
2. Verify the export contains the expected row count and can be restored.
3. In a deliberate maintenance window, truncate the table (`TRUNCATE complaint_history`) after the export is confirmed. This is an explicit operator action, not an application flag or environment-variable bypass.
4. Run the downgrade. `0007` then removes `sequence_number`, and `0006` removes the (now empty) table and reverts `cancelled` to `closed`.
5. Document that restored history after such a downgrade is an external archive, not live data, and that the `cancelled`/`closed` distinction is lost in the downgraded schema.

Do not claim the downgrade is reversible without qualification. It is schema-reversible but audit-data-destructive once history exists.

## 6. Equipment serial uniqueness is exact-match and global

- `equipment` enforces a global uniqueness constraint on `(manufacturer, serial_number)`. The comparison is case-sensitive and applies across all customers.
- `serial_number` is nullable. PostgreSQL unique constraints allow multiple rows with `NULL` serial numbers, so equipment may be recorded without a serial number.
- Whether serial comparison should be case-insensitive, manufacturer-scoped or normalized is an unresolved product decision. The current policy follows the database constraint and must not be changed without a migration and an explicit decision.
