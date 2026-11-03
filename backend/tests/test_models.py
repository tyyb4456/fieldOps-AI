from __future__ import annotations

import uuid

from sqlalchemy import DateTime, inspect
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import configure_mappers

from app.db.base import Base
from app.models import (
    Complaint,
    CompletionReport,
    Conversation,
    Customer,
    Document,
    DocumentChunk,
    Equipment,
    Message,
    ServiceRecord,
    Technician,
    TechnicianAssignment,
    User,
    WorkOrder,
    WorkflowRun,
)

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

EXPECTED_MODELS = {
    "User": User,
    "Customer": Customer,
    "Technician": Technician,
    "Equipment": Equipment,
    "Complaint": Complaint,
    "Conversation": Conversation,
    "Message": Message,
    "WorkOrder": WorkOrder,
    "TechnicianAssignment": TechnicianAssignment,
    "ServiceRecord": ServiceRecord,
    "CompletionReport": CompletionReport,
    "Document": Document,
    "DocumentChunk": DocumentChunk,
    "WorkflowRun": WorkflowRun,
}

EXPECTED_RELATIONSHIPS = {
    User: {"customer", "technician"},
    Customer: {"user", "equipment", "complaints"},
    Technician: {"user", "assignments", "service_records"},
    Equipment: {
        "customer",
        "complaints",
        "work_orders",
        "service_records",
    },
    Complaint: {
        "customer",
        "equipment",
        "conversations",
        "work_order",
        "workflow_runs",
    },
    Conversation: {"complaint", "messages"},
    Message: {"conversation"},
    WorkOrder: {
        "complaint",
        "equipment",
        "assignments",
        "service_records",
        "completion_reports",
    },
    TechnicianAssignment: {"work_order", "technician"},
    ServiceRecord: {"equipment", "work_order", "technician"},
    CompletionReport: {"work_order"},
    Document: {"chunks"},
    DocumentChunk: {"document"},
    WorkflowRun: {"complaint"},
}


def test_all_fourteen_models_are_registered() -> None:
    configure_mappers()

    table_names = set(Base.metadata.tables)
    assert table_names == EXPECTED_TABLES
    assert len(table_names) == 14

    for name, model in EXPECTED_MODELS.items():
        assert model.__name__ == name
        assert issubclass(model, Base)
        assert model.__table__ is Base.metadata.tables[
            model.__tablename__
        ]


def test_every_model_uses_uuid_primary_key_with_server_default() -> None:
    for table in Base.metadata.tables.values():
        primary_key = table.primary_key
        assert [column.name for column in primary_key.columns] == ["id"]
        id_column = primary_key.columns["id"]
        assert id_column.type.python_type is uuid.UUID
        assert id_column.server_default is not None
        assert "gen_random_uuid" in str(id_column.server_default.arg)


def test_relationships_are_configured() -> None:
    configure_mappers()

    for model, expected in EXPECTED_RELATIONSHIPS.items():
        relationships = inspect(model).relationships
        assert set(relationships.keys()) == expected

    assert inspect(User).relationships["customer"].uselist is False
    assert inspect(User).relationships["technician"].uselist is False
    assert inspect(Complaint).relationships["work_order"].uselist is False
    assert inspect(Document).relationships["chunks"].uselist is True
    assert (
        inspect(Document).relationships["chunks"].cascade.delete_orphan
        is True
    )


def test_jsonb_columns_are_declared() -> None:
    jsonb_columns = {
        (Technician.__tablename__, "skills"),
        (Complaint.__tablename__, "reported_symptoms"),
        (WorkOrder.__tablename__, "diagnostic_checklist"),
        (ServiceRecord.__tablename__, "parts_used"),
        (DocumentChunk.__tablename__, "metadata"),
    }

    for table_name, column_name in jsonb_columns:
        column = Base.metadata.tables[table_name].c[column_name]
        assert isinstance(column.type, JSONB)


def test_timestamps_are_timezone_aware() -> None:
    timestamp_columns = {
        (User.__tablename__, "created_at"),
        (Complaint.__tablename__, "created_at"),
        (Complaint.__tablename__, "updated_at"),
        (WorkOrder.__tablename__, "created_at"),
        (WorkOrder.__tablename__, "updated_at"),
        (TechnicianAssignment.__tablename__, "assigned_at"),
        (ServiceRecord.__tablename__, "recorded_at"),
        (CompletionReport.__tablename__, "submitted_at"),
        (WorkflowRun.__tablename__, "started_at"),
    }

    for table_name, column_name in timestamp_columns:
        column = Base.metadata.tables[table_name].c[column_name]
        assert isinstance(column.type, DateTime)
        assert column.type.timezone is True


def test_embedding_column_is_intentionally_deferred() -> None:
    assert "embedding" not in DocumentChunk.__table__.c


def test_composite_integrity_constraints_are_registered() -> None:
    expected_constraints = {
        ("complaints", "fk_complaints_equipment_customer"),
        ("work_orders", "fk_work_orders_complaint_equipment"),
        ("service_records", "fk_service_records_work_order_equipment"),
    }

    for table_name, constraint_name in expected_constraints:
        constraint_names = {
            constraint.name
            for constraint in Base.metadata.tables[table_name].constraints
        }
        assert constraint_name in constraint_names
