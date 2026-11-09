from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING

import pytest
from alembic import command
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import IntegrityError

if TYPE_CHECKING:
    from tests.conftest import MigrationDatabase

EXPECTED_TABLES = {
    "users",
    "customers",
    "technicians",
    "equipment",
    "complaints",
    "complaint_history",
    "conversations",
    "messages",
    "work_orders",
    "technician_assignments",
    "service_records",
    "completion_reports",
    "documents",
    "document_chunks",
    "workflow_runs",
}


def _sync_url(url: str) -> URL:
    return make_url(url).set(drivername="postgresql+psycopg2")


@contextmanager
def _sync_engine(database: MigrationDatabase) -> Iterator[Engine]:
    engine = create_engine(
        _sync_url(database.url),
        pool_pre_ping=True,
    )
    try:
        yield engine
    finally:
        engine.dispose()


def _table_names(database: MigrationDatabase) -> set[str]:
    with _sync_engine(database) as engine:
        return set(inspect(engine).get_table_names())


def test_fresh_database_upgrade_creates_all_tables(
    empty_migration_database: MigrationDatabase,
) -> None:
    command.upgrade(empty_migration_database.config, "head")

    assert _table_names(empty_migration_database) == (
        EXPECTED_TABLES | {"alembic_version"}
    )


def test_expected_constraints_and_indexes_exist(
    empty_migration_database: MigrationDatabase,
) -> None:
    command.upgrade(empty_migration_database.config, "head")

    with _sync_engine(empty_migration_database) as engine:
        inspector = inspect(engine)

        user_checks = {
            check["name"] for check in inspector.get_check_constraints("users")
        }
        assert "ck_users_user_role" in user_checks

        complaint_checks = {
            check["name"] for check in inspector.get_check_constraints("complaints")
        }
        assert {
            "ck_complaints_complaint_channel",
            "ck_complaints_complaint_priority",
            "ck_complaints_complaint_status",
        } <= complaint_checks

        work_order_checks = {
            check["name"] for check in inspector.get_check_constraints("work_orders")
        }
        assert {
            "ck_work_orders_work_order_priority",
            "ck_work_orders_work_order_status",
        } <= work_order_checks

        complaint_fks = {
            fk["name"]: fk for fk in inspector.get_foreign_keys("complaints")
        }
        assert set(
            complaint_fks["fk_complaints_equipment_customer"]["constrained_columns"]
        ) == {"equipment_id", "customer_id"}
        assert set(
            complaint_fks["fk_complaints_equipment_customer"]["referred_columns"]
        ) == {"id", "customer_id"}

        work_order_fks = {
            fk["name"]: fk for fk in inspector.get_foreign_keys("work_orders")
        }
        assert set(
            work_order_fks["fk_work_orders_complaint_equipment"]["constrained_columns"]
        ) == {"complaint_id", "equipment_id"}

        service_record_fks = {
            fk["name"]: fk for fk in inspector.get_foreign_keys("service_records")
        }
        assert set(
            service_record_fks["fk_service_records_work_order_equipment"][
                "constrained_columns"
            ]
        ) == {"work_order_id", "equipment_id"}

        service_record_uniques = {
            unique["name"]
            for unique in inspector.get_unique_constraints("service_records")
        }
        assert "uq_service_records_id_work_order_id" in (service_record_uniques)

        report_columns = {
            column["name"]: column
            for column in inspector.get_columns("completion_reports")
        }
        assert report_columns["service_record_id"]["nullable"] is True

        report_uniques = {
            unique["name"]
            for unique in inspector.get_unique_constraints("completion_reports")
        }
        assert "uq_completion_reports_work_order_id" in report_uniques

        report_fks = {
            fk["name"]: fk for fk in inspector.get_foreign_keys("completion_reports")
        }
        association_fk = report_fks["fk_completion_reports_service_record_work_order"]
        assert set(association_fk["constrained_columns"]) == {
            "service_record_id",
            "work_order_id",
        }
        assert set(association_fk["referred_columns"]) == {
            "id",
            "work_order_id",
        }

        report_indexes = {
            index["name"] for index in inspector.get_indexes("completion_reports")
        }
        assert "ix_completion_reports_work_order_id" not in report_indexes

        work_order_uniques = {
            unique["name"] for unique in inspector.get_unique_constraints("work_orders")
        }
        assert "uq_work_orders_complaint_id" in work_order_uniques

        message_uniques = {
            unique["name"] for unique in inspector.get_unique_constraints("messages")
        }
        assert "uq_messages_external_message_id" in message_uniques

        equipment_indexes = {
            index["name"] for index in inspector.get_indexes("equipment")
        }
        assert "ix_equipment_customer_id" in equipment_indexes

        complaint_indexes = {
            index["name"] for index in inspector.get_indexes("complaints")
        }
        assert {
            "ix_complaints_customer_id",
            "ix_complaints_equipment_id",
            "ix_complaints_status",
        } <= complaint_indexes

        history_indexes = {
            index["name"] for index in inspector.get_indexes("complaint_history")
        }
        assert {
            "ix_complaint_history_complaint_id",
            "ix_complaint_history_created_at",
        } <= history_indexes

        history_uniques = {
            unique["name"]
            for unique in inspector.get_unique_constraints("complaint_history")
        }
        assert "uq_complaint_history_complaint_sequence" in history_uniques

        history_columns = {
            column["name"]: column
            for column in inspector.get_columns("complaint_history")
        }
        assert history_columns["sequence_number"]["nullable"] is False

        history_fks = {
            fk["name"]: fk for fk in inspector.get_foreign_keys("complaint_history")
        }
        assert (
            history_fks["fk_complaint_history_complaint_id_complaints"][
                "referred_table"
            ]
            == "complaints"
        )
        assert (
            history_fks["fk_complaint_history_actor_id_users"]["referred_table"]
            == "users"
        )

        document_columns = {
            column["name"]: column for column in inspector.get_columns("documents")
        }
        assert document_columns["storage_key"]["nullable"] is True
        assert document_columns["file_path"]["nullable"] is True
        assert document_columns["ingestion_status"]["nullable"] is False
        assert "pending" in document_columns["ingestion_status"]["default"]

        document_checks = {
            check["name"] for check in inspector.get_check_constraints("documents")
        }
        assert {
            "ck_documents_ingestion_status",
            "ck_documents_byte_size_non_negative",
            "ck_documents_checksum_sha256_format",
            "ck_documents_active_requires_ready",
        } <= document_checks

        document_uniques = {
            unique["name"] for unique in inspector.get_unique_constraints("documents")
        }
        assert "uq_documents_storage_key" in document_uniques

        document_indexes = {
            index["name"] for index in inspector.get_indexes("documents")
        }
        assert "ix_documents_ingestion_status" in document_indexes

        document_fks = {
            fk["name"]: fk for fk in inspector.get_foreign_keys("documents")
        }
        assert (
            document_fks["fk_documents_uploaded_by_id_users"]["referred_table"]
            == "users"
        )


def test_downgrade_and_reupgrade(
    empty_migration_database: MigrationDatabase,
) -> None:
    command.upgrade(empty_migration_database.config, "head")
    assert _table_names(empty_migration_database) == (
        EXPECTED_TABLES | {"alembic_version"}
    )

    command.downgrade(empty_migration_database.config, "base")
    assert _table_names(empty_migration_database) == {"alembic_version"}

    command.upgrade(empty_migration_database.config, "head")
    assert _table_names(empty_migration_database) == (
        EXPECTED_TABLES | {"alembic_version"}
    )


def test_alembic_check_reports_no_schema_drift(
    empty_migration_database: MigrationDatabase,
) -> None:
    command.upgrade(empty_migration_database.config, "head")
    command.check(empty_migration_database.config)


def test_document_migration_preserves_existing_rows_and_changes_default(
    empty_migration_database: MigrationDatabase,
) -> None:
    command.upgrade(empty_migration_database.config, "2dc9e9936fec")

    with _sync_engine(empty_migration_database) as engine:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO documents "
                    "(manufacturer, model, document_name, version, "
                    "file_path, is_active) "
                    "VALUES ('Acme', 'INV-5000', 'Existing Manual', "
                    "NULL, 'existing.pdf', TRUE)"
                )
            )

    command.upgrade(empty_migration_database.config, "head")

    with _sync_engine(empty_migration_database) as engine:
        with engine.begin() as connection:
            existing = connection.execute(
                text(
                    "SELECT is_active, ingestion_status, file_path, "
                    "storage_key FROM documents "
                    "WHERE document_name = 'Existing Manual'"
                )
            ).one()
            new_is_active = connection.execute(
                text(
                    "INSERT INTO documents "
                    "(manufacturer, model, document_name, file_path) "
                    "VALUES ('Acme', 'INV-5000', 'New Manual', 'new.pdf') "
                    "RETURNING is_active"
                )
            ).scalar_one()

    assert existing.is_active is False
    assert existing.ingestion_status == "pending"
    assert existing.file_path == "existing.pdf"
    assert existing.storage_key is None
    assert new_is_active is False


def test_document_migration_aborts_on_duplicate_null_versions(
    empty_migration_database: MigrationDatabase,
) -> None:
    command.upgrade(empty_migration_database.config, "2dc9e9936fec")

    with _sync_engine(empty_migration_database) as engine:
        with engine.begin() as connection:
            for file_path in ("first.pdf", "second.pdf"):
                connection.execute(
                    text(
                        "INSERT INTO documents "
                        "(manufacturer, model, document_name, version, "
                        "file_path, is_active) "
                        "VALUES ('Acme', 'INV-5000', 'Duplicate Manual', "
                        "NULL, :file_path, TRUE)"
                    ),
                    {"file_path": file_path},
                )

    with pytest.raises(RuntimeError, match="duplicate documents"):
        command.upgrade(empty_migration_database.config, "head")

    with _sync_engine(empty_migration_database) as engine:
        with engine.begin() as connection:
            version = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            document_count = connection.execute(
                text("SELECT count(*) FROM documents")
            ).scalar_one()

    assert version == "2dc9e9936fec"
    assert document_count == 2


def test_clerk_identity_migration_preserves_existing_users(
    empty_migration_database: MigrationDatabase,
) -> None:
    command.upgrade(empty_migration_database.config, "0002_document_integrity")

    with _sync_engine(empty_migration_database) as engine:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users "
                    "(full_name, email, password_hash, role) "
                    "VALUES ('Existing User', 'existing@example.com', "
                    "'legacy-hash', 'customer')"
                )
            )

    command.upgrade(empty_migration_database.config, "head")

    with _sync_engine(empty_migration_database) as engine:
        inspector = inspect(engine)
        columns = {column["name"]: column for column in inspector.get_columns("users")}
        uniques = {
            unique["name"] for unique in inspector.get_unique_constraints("users")
        }

        with engine.begin() as connection:
            row = connection.execute(
                text(
                    "SELECT full_name, email, password_hash, clerk_user_id "
                    "FROM users WHERE email = 'existing@example.com'"
                )
            ).one()

    assert columns["clerk_user_id"]["nullable"] is True
    assert columns["password_hash"]["nullable"] is True
    assert "uq_users_clerk_user_id" in uniques
    assert row.full_name == "Existing User"
    assert row.email == "existing@example.com"
    assert row.password_hash == "legacy-hash"
    assert row.clerk_user_id is None

    command.downgrade(
        empty_migration_database.config,
        "0002_document_integrity",
    )

    with _sync_engine(empty_migration_database) as engine:
        columns = {
            column["name"]: column for column in inspect(engine).get_columns("users")
        }

    assert "clerk_user_id" not in columns
    assert columns["password_hash"]["nullable"] is False


def test_clerk_identity_migration_downgrade_requires_password_hashes(
    empty_migration_database: MigrationDatabase,
) -> None:
    command.upgrade(empty_migration_database.config, "head")

    with _sync_engine(empty_migration_database) as engine:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users "
                    "(full_name, email, clerk_user_id, password_hash, role) "
                    "VALUES ('Clerk User', 'clerk@example.com', "
                    "'user_clerk_test', NULL, 'customer')"
                )
            )

    with pytest.raises(RuntimeError, match="password_hash"):
        command.downgrade(
            empty_migration_database.config,
            "0002_document_integrity",
        )

    with _sync_engine(empty_migration_database) as engine:
        with engine.begin() as connection:
            version = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            clerk_user_id = connection.execute(
                text(
                    "SELECT clerk_user_id FROM users WHERE email = 'clerk@example.com'"
                )
            ).scalar_one()

    assert version == "0011_document_integrity"
    assert clerk_user_id == "user_clerk_test"


def test_email_normalization_migration_normalizes_existing_rows(
    empty_migration_database: MigrationDatabase,
) -> None:
    command.upgrade(
        empty_migration_database.config,
        "0003_clerk_identity",
    )

    with _sync_engine(empty_migration_database) as engine:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users (full_name, email, role) VALUES "
                    "('Mixed', '  Mixed@Example.COM  ', 'customer'), "
                    "('Plain', 'plain@example.com', 'customer')"
                )
            )

    command.upgrade(
        empty_migration_database.config,
        "0004_normalize_emails",
    )

    with _sync_engine(empty_migration_database) as engine:
        with engine.begin() as connection:
            rows = connection.execute(
                text("SELECT full_name, email FROM users ORDER BY full_name")
            ).all()

    assert (rows[0].full_name, rows[0].email) == (
        "Mixed",
        "mixed@example.com",
    )
    assert (rows[1].full_name, rows[1].email) == (
        "Plain",
        "plain@example.com",
    )


def test_email_normalization_migration_aborts_on_duplicates(
    empty_migration_database: MigrationDatabase,
) -> None:
    command.upgrade(
        empty_migration_database.config,
        "0003_clerk_identity",
    )

    with _sync_engine(empty_migration_database) as engine:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users (full_name, email, role) VALUES "
                    "('First', 'dup@example.com', 'customer'), "
                    "('Second', 'Dup@Example.com', 'customer')"
                )
            )

    with pytest.raises(RuntimeError, match="case-insensitive"):
        command.upgrade(
            empty_migration_database.config,
            "0004_normalize_emails",
        )

    with _sync_engine(empty_migration_database) as engine:
        with engine.begin() as connection:
            version = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()

    assert version == "0003_clerk_identity"


def test_complaint_cancellation_migration_backfills_closed_status(
    empty_migration_database: MigrationDatabase,
) -> None:
    command.upgrade(
        empty_migration_database.config,
        "0005_profile_enrichment",
    )

    with _sync_engine(empty_migration_database) as engine:
        with engine.begin() as connection:
            user_id = connection.execute(
                text(
                    "INSERT INTO users (full_name, email, role) "
                    "VALUES ('Legacy', 'legacy@example.com', 'customer') "
                    "RETURNING id"
                )
            ).scalar_one()
            customer_id = connection.execute(
                text("INSERT INTO customers (user_id) VALUES (:user_id) RETURNING id"),
                {"user_id": user_id},
            ).scalar_one()
            complaint_id = connection.execute(
                text(
                    "INSERT INTO complaints "
                    "(customer_id, description, channel, status) "
                    "VALUES (:customer_id, 'Legacy complaint', 'web', "
                    "'closed') RETURNING id"
                ),
                {"customer_id": customer_id},
            ).scalar_one()

    command.upgrade(empty_migration_database.config, "head")

    with _sync_engine(empty_migration_database) as engine:
        with engine.begin() as connection:
            status = connection.execute(
                text("SELECT status FROM complaints WHERE id = :id"),
                {"id": complaint_id},
            ).scalar_one()
            history_count = connection.execute(
                text("SELECT count(*) FROM complaint_history")
            ).scalar_one()

    assert status == "cancelled"
    assert history_count == 0

    command.downgrade(
        empty_migration_database.config,
        "0005_profile_enrichment",
    )

    with _sync_engine(empty_migration_database) as engine:
        with engine.begin() as connection:
            status = connection.execute(
                text("SELECT status FROM complaints WHERE id = :id"),
                {"id": complaint_id},
            ).scalar_one()
        assert "complaint_history" not in _table_names(empty_migration_database)

    assert status == "closed"


def test_profile_enrichment_migration_adds_and_removes_columns(
    empty_migration_database: MigrationDatabase,
) -> None:
    command.upgrade(empty_migration_database.config, "head")

    with _sync_engine(empty_migration_database) as engine:
        columns = {
            column["name"]: column for column in inspect(engine).get_columns("users")
        }

    assert columns["profile_enrichment_attempts"]["nullable"] is False
    assert columns["profile_enrichment_last_attempt_at"]["nullable"] is True
    assert columns["profile_enriched_at"]["nullable"] is True

    command.downgrade(
        empty_migration_database.config,
        "0004_normalize_emails",
    )

    with _sync_engine(empty_migration_database) as engine:
        columns = {column["name"] for column in inspect(engine).get_columns("users")}

    assert "profile_enrichment_attempts" not in columns
    assert "profile_enrichment_last_attempt_at" not in columns
    assert "profile_enriched_at" not in columns


def _insert_legacy_complaint(connection) -> object:
    user_id = connection.execute(
        text(
            "INSERT INTO users (full_name, email, role) "
            "VALUES ('History', :email, 'customer') "
            "RETURNING id"
        ),
        {"email": f"history_{uuid.uuid4().hex}@example.com"},
    ).scalar_one()
    customer_id = connection.execute(
        text("INSERT INTO customers (user_id) VALUES (:user_id) RETURNING id"),
        {"user_id": user_id},
    ).scalar_one()
    return connection.execute(
        text(
            "INSERT INTO complaints "
            "(customer_id, description, channel, status) "
            "VALUES (:customer_id, 'History complaint', 'web', 'received') "
            "RETURNING id"
        ),
        {"customer_id": customer_id},
    ).scalar_one()


def _insert_legacy_history(
    connection,
    complaint_id: object,
    event_type: str,
    created_at: str,
) -> None:
    connection.execute(
        text(
            "INSERT INTO complaint_history "
            "(complaint_id, event_type, changed_fields, created_at) "
            "VALUES (:complaint_id, :event_type, '{}'::jsonb, "
            "CAST(:created_at AS timestamptz))"
        ),
        {
            "complaint_id": complaint_id,
            "event_type": event_type,
            "created_at": created_at,
        },
    )


def test_complaint_history_sequence_migration_backfills_existing_rows(
    empty_migration_database: MigrationDatabase,
) -> None:
    command.upgrade(
        empty_migration_database.config,
        "0006_complaint_lifecycle",
    )

    with _sync_engine(empty_migration_database) as engine:
        with engine.begin() as connection:
            first_complaint = _insert_legacy_complaint(connection)
            second_complaint = _insert_legacy_complaint(connection)
            _insert_legacy_history(
                connection,
                first_complaint,
                "updated",
                "2026-01-02T00:00:00+00:00",
            )
            _insert_legacy_history(
                connection,
                first_complaint,
                "created",
                "2026-01-01T00:00:00+00:00",
            )
            _insert_legacy_history(
                connection,
                first_complaint,
                "cancelled",
                "2026-01-03T00:00:00+00:00",
            )
            _insert_legacy_history(
                connection,
                second_complaint,
                "created",
                "2026-02-01T00:00:00+00:00",
            )

    command.upgrade(empty_migration_database.config, "head")

    with _sync_engine(empty_migration_database) as engine:
        with engine.begin() as connection:
            rows = connection.execute(
                text(
                    "SELECT complaint_id, event_type, sequence_number "
                    "FROM complaint_history "
                    "ORDER BY complaint_id, sequence_number"
                )
            ).all()

    by_complaint: dict[object, list[tuple[str, int]]] = {}
    for row in rows:
        by_complaint.setdefault(row.complaint_id, []).append(
            (row.event_type, row.sequence_number)
        )

    assert by_complaint[first_complaint] == [
        ("created", 1),
        ("updated", 2),
        ("cancelled", 3),
    ]
    assert by_complaint[second_complaint] == [("created", 1)]


def test_complaint_history_downgrade_refuses_and_requires_archival(
    empty_migration_database: MigrationDatabase,
) -> None:
    command.upgrade(empty_migration_database.config, "head")

    with _sync_engine(empty_migration_database) as engine:
        with engine.begin() as connection:
            complaint_id = _insert_legacy_complaint(connection)
            connection.execute(
                text(
                    "INSERT INTO complaint_history "
                    "(complaint_id, sequence_number, event_type, "
                    "changed_fields) "
                    "VALUES (:complaint_id, 1, 'created', '{}'::jsonb)"
                ),
                {"complaint_id": complaint_id},
            )

    with pytest.raises(RuntimeError, match="Refusing to downgrade"):
        command.downgrade(
            empty_migration_database.config,
            "0005_profile_enrichment",
        )

    with _sync_engine(empty_migration_database) as engine:
        with engine.begin() as connection:
            version = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            count = connection.execute(
                text("SELECT count(*) FROM complaint_history")
            ).scalar_one()
            archived = connection.execute(
                text(
                    "SELECT complaint_id, sequence_number, event_type "
                    "FROM complaint_history "
                    "ORDER BY complaint_id, sequence_number"
                )
            ).all()

    assert version == "0011_document_integrity"
    assert count == 1
    assert archived[0].complaint_id == complaint_id
    assert archived[0].sequence_number == 1

    # Documented archival procedure: the export above has been verified, so
    # the operator deliberately empties the audit table before retrying.
    with _sync_engine(empty_migration_database) as engine:
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM complaint_history"))

    command.downgrade(
        empty_migration_database.config,
        "0005_profile_enrichment",
    )

    assert "complaint_history" not in _table_names(empty_migration_database)


def test_completion_report_link_migration_adds_and_removes_association(
    empty_migration_database: MigrationDatabase,
) -> None:
    command.upgrade(empty_migration_database.config, "head")

    with _sync_engine(empty_migration_database) as engine:
        inspector = inspect(engine)
        columns = {
            column["name"] for column in inspector.get_columns("completion_reports")
        }
        report_uniques = {
            unique["name"]
            for unique in inspector.get_unique_constraints("completion_reports")
        }
        service_record_uniques = {
            unique["name"]
            for unique in inspector.get_unique_constraints("service_records")
        }
        report_indexes = {
            index["name"] for index in inspector.get_indexes("completion_reports")
        }

    assert "service_record_id" in columns
    assert "uq_completion_reports_work_order_id" in report_uniques
    assert "uq_service_records_id_work_order_id" in service_record_uniques
    assert "ix_completion_reports_work_order_id" not in report_indexes

    command.downgrade(
        empty_migration_database.config,
        "0008_active_assignment_unique",
    )

    with _sync_engine(empty_migration_database) as engine:
        inspector = inspect(engine)
        columns = {
            column["name"] for column in inspector.get_columns("completion_reports")
        }
        report_uniques = {
            unique["name"]
            for unique in inspector.get_unique_constraints("completion_reports")
        }
        service_record_uniques = {
            unique["name"]
            for unique in inspector.get_unique_constraints("service_records")
        }
        report_indexes = {
            index["name"] for index in inspector.get_indexes("completion_reports")
        }

    assert "service_record_id" not in columns
    assert "uq_completion_reports_work_order_id" not in report_uniques
    assert "uq_service_records_id_work_order_id" not in service_record_uniques
    assert "ix_completion_reports_work_order_id" in report_indexes


def test_completion_report_link_migration_aborts_on_duplicate_reports(
    empty_migration_database: MigrationDatabase,
) -> None:
    command.upgrade(
        empty_migration_database.config,
        "0008_active_assignment_unique",
    )

    with _sync_engine(empty_migration_database) as engine:
        with engine.begin() as connection:
            user_id = connection.execute(
                text(
                    "INSERT INTO users (full_name, email, role) "
                    "VALUES ('Report Owner', :email, 'customer') "
                    "RETURNING id"
                ),
                {"email": f"report_{uuid.uuid4().hex}@example.com"},
            ).scalar_one()
            customer_id = connection.execute(
                text("INSERT INTO customers (user_id) VALUES (:user_id) RETURNING id"),
                {"user_id": user_id},
            ).scalar_one()
            equipment_id = connection.execute(
                text(
                    "INSERT INTO equipment "
                    "(customer_id, manufacturer, model, serial_number, "
                    "equipment_type) VALUES (:customer_id, 'Acme', "
                    "'INV-5000', :serial, 'solar_inverter') RETURNING id"
                ),
                {
                    "customer_id": customer_id,
                    "serial": uuid.uuid4().hex[:12],
                },
            ).scalar_one()
            complaint_id = connection.execute(
                text(
                    "INSERT INTO complaints "
                    "(customer_id, equipment_id, description, channel, "
                    "status) VALUES (:customer_id, :equipment_id, "
                    "'Legacy complaint', 'web', 'received') RETURNING id"
                ),
                {
                    "customer_id": customer_id,
                    "equipment_id": equipment_id,
                },
            ).scalar_one()
            work_order_id = connection.execute(
                text(
                    "INSERT INTO work_orders "
                    "(complaint_id, equipment_id, title, description) "
                    "VALUES (:complaint_id, :equipment_id, 'Inspect', "
                    "'Legacy work order') RETURNING id"
                ),
                {
                    "complaint_id": complaint_id,
                    "equipment_id": equipment_id,
                },
            ).scalar_one()
            for summary in ("First report", "Second report"):
                connection.execute(
                    text(
                        "INSERT INTO completion_reports "
                        "(work_order_id, summary) "
                        "VALUES (:work_order_id, :summary)"
                    ),
                    {
                        "work_order_id": work_order_id,
                        "summary": summary,
                    },
                )

    with pytest.raises(RuntimeError, match="one completion report"):
        command.upgrade(empty_migration_database.config, "head")

    with _sync_engine(empty_migration_database) as engine:
        with engine.begin() as connection:
            version = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            report_count = connection.execute(
                text("SELECT count(*) FROM completion_reports")
            ).scalar_one()

    assert version == "0008_active_assignment_unique"
    assert report_count == 2


def test_document_storage_migration_backfills_legacy_rows(
    empty_migration_database: MigrationDatabase,
) -> None:
    command.upgrade(
        empty_migration_database.config,
        "0009_completion_report_link",
    )

    with _sync_engine(empty_migration_database) as engine:
        with engine.begin() as connection:
            document_id = connection.execute(
                text(
                    "INSERT INTO documents "
                    "(manufacturer, model, document_name, version, "
                    "file_path, is_active) "
                    "VALUES ('Acme', 'INV-5000', 'Legacy Manual', '1.0', "
                    "'legacy/INV-5000.pdf', TRUE) RETURNING id"
                )
            ).scalar_one()
            connection.execute(
                text(
                    "INSERT INTO document_chunks "
                    "(document_id, chunk_index, content) "
                    "VALUES (:document_id, 0, 'Legacy chunk')"
                ),
                {"document_id": document_id},
            )

    command.upgrade(empty_migration_database.config, "head")

    with _sync_engine(empty_migration_database) as engine:
        with engine.begin() as connection:
            row = connection.execute(
                text(
                    "SELECT is_active, ingestion_status, file_path, "
                    "storage_key, original_filename, content_type, "
                    "byte_size, checksum_sha256, uploaded_by_id, "
                    "ingested_at FROM documents WHERE id = :id"
                ),
                {"id": document_id},
            ).one()
            chunk_count = connection.execute(
                text("SELECT count(*) FROM document_chunks WHERE document_id = :id"),
                {"id": document_id},
            ).scalar_one()

    assert row.is_active is False
    assert row.ingestion_status == "pending"
    assert row.file_path == "legacy/INV-5000.pdf"
    assert row.storage_key is None
    assert row.original_filename is None
    assert row.content_type is None
    assert row.byte_size is None
    assert row.checksum_sha256 is None
    assert row.uploaded_by_id is None
    assert row.ingested_at is None
    assert chunk_count == 1

    with _sync_engine(empty_migration_database) as engine:
        with engine.begin() as connection:
            with pytest.raises(IntegrityError):
                connection.execute(
                    text("UPDATE documents SET is_active = TRUE WHERE id = :id"),
                    {"id": document_id},
                )


def test_document_storage_migration_downgrade_refuses_storage_backed_rows(
    empty_migration_database: MigrationDatabase,
) -> None:
    command.upgrade(empty_migration_database.config, "head")

    with _sync_engine(empty_migration_database) as engine:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO documents "
                    "(manufacturer, model, document_name, storage_key, "
                    "content_type, byte_size, checksum_sha256, "
                    "ingestion_status) "
                    "VALUES ('Acme', 'INV-5000', 'Stored Manual', "
                    "'aa/abcd.pdf', 'application/pdf', 12, :checksum, "
                    "'ready')"
                ),
                {"checksum": "a" * 64},
            )

    with pytest.raises(RuntimeError, match="Refusing to downgrade"):
        command.downgrade(
            empty_migration_database.config,
            "0009_completion_report_link",
        )

    with _sync_engine(empty_migration_database) as engine:
        with engine.begin() as connection:
            version = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            storage_key = connection.execute(
                text(
                    "SELECT storage_key FROM documents "
                    "WHERE document_name = 'Stored Manual'"
                )
            ).scalar_one()

    assert version == "0011_document_integrity"
    assert storage_key == "aa/abcd.pdf"

    with _sync_engine(empty_migration_database) as engine:
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM documents WHERE document_name = 'Stored Manual'")
            )

    command.downgrade(
        empty_migration_database.config,
        "0009_completion_report_link",
    )

    with _sync_engine(empty_migration_database) as engine:
        inspector = inspect(engine)
        columns = {
            column["name"]: column for column in inspector.get_columns("documents")
        }

    assert "storage_key" not in columns
    assert "ingestion_status" not in columns
    assert columns["file_path"]["nullable"] is False

    command.upgrade(empty_migration_database.config, "head")

    with _sync_engine(empty_migration_database) as engine:
        columns = {
            column["name"] for column in inspect(engine).get_columns("documents")
        }

    assert "storage_key" in columns
    assert "ingestion_status" in columns


def test_document_integrity_migration_checksum_format_and_recovery_column(
    empty_migration_database: MigrationDatabase,
) -> None:
    command.upgrade(
        empty_migration_database.config,
        "0010_document_storage",
    )

    with _sync_engine(empty_migration_database) as engine:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO documents "
                    "(manufacturer, model, document_name, checksum_sha256) "
                    "VALUES ('Acme', 'INV-5000', 'Invalid Checksum', :value)"
                ),
                {"value": "A" * 64},
            )

    with pytest.raises(RuntimeError, match="lowercase SHA-256"):
        command.upgrade(empty_migration_database.config, "head")

    with _sync_engine(empty_migration_database) as engine:
        with engine.begin() as connection:
            version = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            connection.execute(
                text(
                    "UPDATE documents SET checksum_sha256 = NULL "
                    "WHERE document_name = 'Invalid Checksum'"
                )
            )

    assert version == "0010_document_storage"

    command.upgrade(empty_migration_database.config, "head")

    with _sync_engine(empty_migration_database) as engine:
        inspector = inspect(engine)
        columns = {column["name"] for column in inspector.get_columns("documents")}
        checks = {
            check["name"] for check in inspector.get_check_constraints("documents")
        }

    assert "ingestion_started_at" in columns
    assert "ck_documents_checksum_sha256_format" in checks

    with pytest.raises(IntegrityError):
        with _sync_engine(empty_migration_database) as engine:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO documents "
                        "(manufacturer, model, document_name, "
                        "checksum_sha256) "
                        "VALUES ('Acme', 'INV-5000', 'Uppercase', :value)"
                    ),
                    {"value": "B" * 64},
                )

    with _sync_engine(empty_migration_database) as engine:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO documents "
                    "(manufacturer, model, document_name, checksum_sha256) "
                    "VALUES ('Acme', 'INV-5000', 'Valid', :value)"
                ),
                {"value": "b" * 64},
            )

    command.downgrade(
        empty_migration_database.config,
        "0010_document_storage",
    )

    with _sync_engine(empty_migration_database) as engine:
        inspector = inspect(engine)
        columns = {column["name"] for column in inspector.get_columns("documents")}
        checks = {
            check["name"] for check in inspector.get_check_constraints("documents")
        }

    assert "ingestion_started_at" not in columns
    assert "ck_documents_checksum_sha256_format" not in checks
    assert "ck_documents_checksum_sha256_length" in checks

    with _sync_engine(empty_migration_database) as engine:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO documents "
                    "(manufacturer, model, document_name, checksum_sha256) "
                    "VALUES ('Acme', 'INV-5000', 'Uppercase Allowed', :value)"
                ),
                {"value": "C" * 64},
            )
            connection.execute(
                text("DELETE FROM documents WHERE document_name = 'Uppercase Allowed'")
            )

    command.upgrade(empty_migration_database.config, "head")

    with _sync_engine(empty_migration_database) as engine:
        with engine.begin() as connection:
            version = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()

    assert version == "0011_document_integrity"
