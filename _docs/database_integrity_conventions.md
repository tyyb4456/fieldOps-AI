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
