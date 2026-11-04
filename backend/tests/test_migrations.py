from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING

import pytest
from alembic import command
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.engine import URL, make_url

if TYPE_CHECKING:
    from tests.conftest import MigrationDatabase

EXPECTED_TABLES = {
    "users",
    "customers",
    "technicians",
    "equipment",
    "complaints",
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
            check["name"]
            for check in inspector.get_check_constraints("users")
        }
        assert "ck_users_user_role" in user_checks

        complaint_checks = {
            check["name"]
            for check in inspector.get_check_constraints("complaints")
        }
        assert {
            "ck_complaints_complaint_channel",
            "ck_complaints_complaint_priority",
            "ck_complaints_complaint_status",
        } <= complaint_checks

        work_order_checks = {
            check["name"]
            for check in inspector.get_check_constraints("work_orders")
        }
        assert {
            "ck_work_orders_work_order_priority",
            "ck_work_orders_work_order_status",
        } <= work_order_checks

        complaint_fks = {
            fk["name"]: fk
            for fk in inspector.get_foreign_keys("complaints")
        }
        assert set(
            complaint_fks["fk_complaints_equipment_customer"][
                "constrained_columns"
            ]
        ) == {"equipment_id", "customer_id"}
        assert set(
            complaint_fks["fk_complaints_equipment_customer"][
                "referred_columns"
            ]
        ) == {"id", "customer_id"}

        work_order_fks = {
            fk["name"]: fk
            for fk in inspector.get_foreign_keys("work_orders")
        }
        assert set(
            work_order_fks["fk_work_orders_complaint_equipment"][
                "constrained_columns"
            ]
        ) == {"complaint_id", "equipment_id"}

        service_record_fks = {
            fk["name"]: fk
            for fk in inspector.get_foreign_keys("service_records")
        }
        assert set(
            service_record_fks["fk_service_records_work_order_equipment"][
                "constrained_columns"
            ]
        ) == {"work_order_id", "equipment_id"}

        work_order_uniques = {
            unique["name"]
            for unique in inspector.get_unique_constraints("work_orders")
        }
        assert "uq_work_orders_complaint_id" in work_order_uniques

        message_uniques = {
            unique["name"]
            for unique in inspector.get_unique_constraints("messages")
        }
        assert "uq_messages_external_message_id" in message_uniques

        equipment_indexes = {
            index["name"]
            for index in inspector.get_indexes("equipment")
        }
        assert "ix_equipment_customer_id" in equipment_indexes

        complaint_indexes = {
            index["name"]
            for index in inspector.get_indexes("complaints")
        }
        assert {
            "ix_complaints_customer_id",
            "ix_complaints_equipment_id",
            "ix_complaints_status",
        } <= complaint_indexes


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
            existing_is_active = connection.execute(
                text(
                    "SELECT is_active FROM documents "
                    "WHERE document_name = 'Existing Manual'"
                )
            ).scalar_one()
            new_is_active = connection.execute(
                text(
                    "INSERT INTO documents "
                    "(manufacturer, model, document_name, file_path) "
                    "VALUES ('Acme', 'INV-5000', 'New Manual', 'new.pdf') "
                    "RETURNING is_active"
                )
            ).scalar_one()

    assert existing_is_active is True
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
