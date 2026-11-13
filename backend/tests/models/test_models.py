from __future__ import annotations

import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, inspect
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import configure_mappers

from app.db.base import Base
from app.models import (
    BackgroundTask,
    Complaint,
    ComplaintHistory,
    CompletionReport,
    Conversation,
    Customer,
    Document,
    DocumentChunk,
    DocumentChunkEmbedding,
    Equipment,
    Message,
    OutboxEvent,
    ServiceRecord,
    Technician,
    TechnicianAssignment,
    User,
    WebhookEvent,
    WorkflowRun,
    WorkOrder,
    WorkOrderProposal,
)

EXPECTED_TABLES = {
    "background_tasks",
    "outbox_events",
    "webhook_events",
    "users",
    "customers",
    "technicians",
    "equipment",
    "complaints",
    "complaint_history",
    "conversations",
    "messages",
    "work_orders",
    "work_order_proposals",
    "technician_assignments",
    "service_records",
    "completion_reports",
    "documents",
    "document_chunks",
    "document_chunk_embeddings",
    "workflow_runs",
}

EXPECTED_MODELS = {
    "BackgroundTask": BackgroundTask,
    "OutboxEvent": OutboxEvent,
    "WebhookEvent": WebhookEvent,
    "User": User,
    "Customer": Customer,
    "Technician": Technician,
    "Equipment": Equipment,
    "Complaint": Complaint,
    "ComplaintHistory": ComplaintHistory,
    "Conversation": Conversation,
    "Message": Message,
    "WorkOrder": WorkOrder,
    "WorkOrderProposal": WorkOrderProposal,
    "TechnicianAssignment": TechnicianAssignment,
    "ServiceRecord": ServiceRecord,
    "CompletionReport": CompletionReport,
    "Document": Document,
    "DocumentChunk": DocumentChunk,
    "DocumentChunkEmbedding": DocumentChunkEmbedding,
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
        "work_order_proposals",
        "workflow_runs",
        "history",
    },
    ComplaintHistory: {"complaint"},
    Conversation: {"complaint", "messages"},
    Message: {"conversation"},
    WorkOrder: {
        "complaint",
        "equipment",
        "assignments",
        "service_records",
        "completion_reports",
    },
    WorkOrderProposal: {
        "complaint",
        "selected_technician",
        "created_by",
        "reviewed_by",
        "resulting_work_order",
        "resulting_assignment",
    },
    TechnicianAssignment: {"work_order", "technician"},
    ServiceRecord: {"equipment", "work_order", "technician"},
    CompletionReport: {"work_order", "service_record"},
    Document: {"chunks"},
    DocumentChunk: {"document"},
    DocumentChunkEmbedding: set(),
    WorkflowRun: {"complaint"},
    BackgroundTask: set(),
    OutboxEvent: set(),
    WebhookEvent: set(),
}


def test_all_models_are_registered() -> None:
    configure_mappers()

    table_names = set(Base.metadata.tables)
    assert table_names == EXPECTED_TABLES
    assert len(table_names) == 20

    for name, model in EXPECTED_MODELS.items():
        assert model.__name__ == name
        assert issubclass(model, Base)
        assert model.__table__ is Base.metadata.tables[
            model.__tablename__
        ]


def test_every_model_uses_uuid_primary_key_with_server_default() -> None:
    for table in Base.metadata.tables.values():
        if table.name == DocumentChunkEmbedding.__tablename__:
            continue
        primary_key = table.primary_key
        assert [column.name for column in primary_key.columns] == ["id"]
        id_column = primary_key.columns["id"]
        assert id_column.type.python_type is uuid.UUID
        assert id_column.server_default is not None
        assert "gen_random_uuid" in str(id_column.server_default.arg)

    embedding_id = DocumentChunkEmbedding.__table__.c["id"]
    assert embedding_id.type.python_type is uuid.UUID
    assert embedding_id.server_default is None
    assert [fk.target_fullname for fk in embedding_id.foreign_keys] == [
        "document_chunks.id"
    ]


RESTRICT_RELATIONSHIPS = {
    User: {"customer", "technician"},
    Customer: {"equipment", "complaints"},
    Technician: {"assignments", "service_records"},
    Equipment: {"complaints", "work_orders", "service_records"},
    Complaint: {
        "conversations",
        "work_order",
        "work_order_proposals",
        "workflow_runs",
        "history",
    },
    Conversation: {"messages"},
    WorkOrder: {
        "assignments",
        "service_records",
        "completion_reports",
    },
}


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


def test_restrict_relationships_are_left_to_the_database() -> None:
    configure_mappers()

    for model, relationship_names in RESTRICT_RELATIONSHIPS.items():
        for relationship_name in relationship_names:
            assert (
                inspect(model).relationships[relationship_name].passive_deletes
                == "all"
            )

    assert (
        inspect(Document).relationships["chunks"].passive_deletes is True
    )


def test_jsonb_columns_are_declared() -> None:
    jsonb_columns = {
        (Technician.__tablename__, "skills"),
        (Complaint.__tablename__, "reported_symptoms"),
        (ComplaintHistory.__tablename__, "changed_fields"),
        (WorkOrder.__tablename__, "diagnostic_checklist"),
        (ServiceRecord.__tablename__, "parts_used"),
        (DocumentChunk.__tablename__, "metadata"),
        (DocumentChunkEmbedding.__tablename__, "langchain_metadata"),
        (OutboxEvent.__tablename__, "payload"),
    }

    for table_name, column_name in jsonb_columns:
        column = Base.metadata.tables[table_name].c[column_name]
        assert isinstance(column.type, JSONB)


def test_timestamps_are_timezone_aware() -> None:
    timestamp_columns = {
        (User.__tablename__, "created_at"),
        (Complaint.__tablename__, "created_at"),
        (Complaint.__tablename__, "updated_at"),
        (ComplaintHistory.__tablename__, "created_at"),
        (WorkOrder.__tablename__, "created_at"),
        (WorkOrder.__tablename__, "updated_at"),
        (TechnicianAssignment.__tablename__, "assigned_at"),
        (ServiceRecord.__tablename__, "recorded_at"),
        (CompletionReport.__tablename__, "submitted_at"),
        (WorkflowRun.__tablename__, "started_at"),
        (BackgroundTask.__tablename__, "started_at"),
        (BackgroundTask.__tablename__, "finished_at"),
        (OutboxEvent.__tablename__, "published_at"),
        (OutboxEvent.__tablename__, "created_at"),
        (OutboxEvent.__tablename__, "updated_at"),
        (WebhookEvent.__tablename__, "processed_at"),
    }

    for table_name, column_name in timestamp_columns:
        column = Base.metadata.tables[table_name].c[column_name]
        assert isinstance(column.type, DateTime)
        assert column.type.timezone is True


def test_document_defaults_to_inactive() -> None:
    column = Document.__table__.c["is_active"]

    assert column.default.arg is False
    assert column.server_default is not None
    assert "false" in str(column.server_default.arg)


def test_document_version_uniqueness_uses_nulls_not_distinct() -> None:
    constraint = next(
        constraint
        for constraint in Document.__table__.constraints
        if constraint.name == "uq_documents_manufacturer_model_name_version"
    )

    assert (
        constraint.dialect_options["postgresql"]["nulls_not_distinct"]
        is True
    )


def test_embedding_column_is_intentionally_deferred() -> None:
    assert "embedding" not in DocumentChunk.__table__.c


def test_vector_embedding_column_uses_fixed_pgvector_dimensions() -> None:
    embedding = DocumentChunkEmbedding.__table__.c["embedding"]

    assert isinstance(embedding.type, Vector)
    assert embedding.type.dim == 1536
    assert embedding.nullable is False


def test_composite_integrity_constraints_are_registered() -> None:
    expected_constraints = {
        ("complaints", "fk_complaints_equipment_customer"),
        ("work_orders", "fk_work_orders_complaint_equipment"),
        ("service_records", "fk_service_records_work_order_equipment"),
        (
            "completion_reports",
            "fk_completion_reports_service_record_work_order",
        ),
    }

    for table_name, constraint_name in expected_constraints:
        constraint_names = {
            constraint.name
            for constraint in Base.metadata.tables[table_name].constraints
        }
        assert constraint_name in constraint_names


def test_clerk_identity_is_unique_and_optional() -> None:
    column = User.__table__.c["clerk_user_id"]

    assert column.nullable is True
    assert column.unique is True
    assert column.type.length == 255


def test_password_hash_is_optional_for_clerk_accounts() -> None:
    assert User.__table__.c["password_hash"].nullable is True


def test_complaint_history_sequence_is_unique_per_complaint() -> None:
    table = ComplaintHistory.__table__

    assert table.c["sequence_number"].nullable is False

    constraint = next(
        constraint
        for constraint in table.constraints
        if constraint.name == "uq_complaint_history_complaint_sequence"
    )
    assert [column.name for column in constraint.columns] == [
        "complaint_id",
        "sequence_number",
    ]
