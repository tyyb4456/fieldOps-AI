from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UpdatedAtMixin, UUIDPrimaryKeyMixin
from app.models.enums import (
    Priority,
    WorkOrderProposalStatus,
    enum_type,
)

if TYPE_CHECKING:
    from app.models.complaint import Complaint
    from app.models.technician import Technician
    from app.models.technician_assignment import TechnicianAssignment
    from app.models.user import User
    from app.models.work_order import WorkOrder


class WorkOrderProposal(UUIDPrimaryKeyMixin, UpdatedAtMixin, Base):
    """A reviewable work-order proposal produced by the preparation agent.

    A proposal is deliberately separate from ``WorkOrder``. It records what the
    agent proposed and what a reviewer approved, while the actual work order is
    created only by the deterministic approval service.
    """

    __tablename__ = "work_order_proposals"
    __table_args__ = (
        CheckConstraint(
            "estimated_duration_minutes IS NULL "
            "OR estimated_duration_minutes >= 0",
            name="estimated_duration_non_negative",
        ),
        UniqueConstraint(
            "resulting_work_order_id",
            name="uq_work_order_proposals_resulting_work_order_id",
        ),
        UniqueConstraint(
            "resulting_assignment_id",
            name="uq_work_order_proposals_resulting_assignment_id",
        ),
        Index("ix_work_order_proposals_complaint_id", "complaint_id"),
        Index("ix_work_order_proposals_status", "status"),
        Index("ix_work_order_proposals_created_by_id", "created_by_id"),
        Index(
            "uq_work_order_proposals_pending_complaint",
            "complaint_id",
            unique=True,
            postgresql_where=text("status = 'pending_approval'"),
        ),
    )

    complaint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("complaints.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[WorkOrderProposalStatus] = mapped_column(
        enum_type(
            WorkOrderProposalStatus,
            "work_order_proposal_status",
            length=30,
        ),
        nullable=False,
        default=WorkOrderProposalStatus.PENDING_APPROVAL,
        server_default=WorkOrderProposalStatus.PENDING_APPROVAL.value,
    )

    # Database facts captured when the proposal was generated.
    context_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    # Agent-drafted work-order content.
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    problem_description: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_scope: Mapped[str] = mapped_column(Text, nullable=False)
    technical_findings: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_actions: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    required_skills: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    required_parts: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    priority: Mapped[Priority] = mapped_column(
        enum_type(Priority, "work_order_priority", length=20),
        nullable=False,
    )
    estimated_duration_minutes: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    safety_warnings: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    missing_information: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    generation_warnings: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )

    # Diagnostic evidence, and deterministic technician recommendation output.
    diagnostic_status: Mapped[str] = mapped_column(String(40), nullable=False)
    diagnostic_summary: Mapped[str] = mapped_column(Text, nullable=False)
    diagnostic_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    citations: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    requires_escalation: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=false(),
    )
    escalation_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    technician_recommendations: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )

    # Human review and execution linkage.
    selected_technician_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("technicians.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    rejection_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    resulting_work_order_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("work_orders.id", ondelete="SET NULL"),
        nullable=True,
    )
    resulting_assignment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("technician_assignments.id", ondelete="SET NULL"),
        nullable=True,
    )

    complaint: Mapped[Complaint] = relationship(
        back_populates="work_order_proposals",
        foreign_keys=[complaint_id],
    )
    selected_technician: Mapped[Technician | None] = relationship(
        foreign_keys=[selected_technician_id],
    )
    created_by: Mapped[User | None] = relationship(
        foreign_keys=[created_by_id],
    )
    reviewed_by: Mapped[User | None] = relationship(
        foreign_keys=[reviewed_by_id],
    )
    resulting_work_order: Mapped[WorkOrder | None] = relationship(
        foreign_keys=[resulting_work_order_id],
    )
    resulting_assignment: Mapped[TechnicianAssignment | None] = relationship(
        foreign_keys=[resulting_assignment_id],
    )

    def __repr__(self) -> str:
        return (
            f"WorkOrderProposal(id={self.id!r}, status={self.status!r})"
        )
