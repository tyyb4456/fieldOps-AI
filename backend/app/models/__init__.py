from __future__ import annotations

from app.models.background_task import BackgroundTask
from app.models.complaint import Complaint
from app.models.complaint_history import ComplaintHistory
from app.models.completion_report import CompletionReport
from app.models.conversation import Conversation
from app.models.customer import Customer
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.document_chunk_embedding import DocumentChunkEmbedding
from app.models.equipment import Equipment
from app.models.message import Message
from app.models.outbox_event import OutboxEvent
from app.models.service_record import ServiceRecord
from app.models.technician import Technician
from app.models.technician_assignment import TechnicianAssignment
from app.models.user import User
from app.models.webhook_event import WebhookEvent
from app.models.work_order import WorkOrder
from app.models.work_order_proposal import WorkOrderProposal
from app.models.workflow_run import WorkflowRun

__all__ = [
    "BackgroundTask",
    "Complaint",
    "ComplaintHistory",
    "CompletionReport",
    "Conversation",
    "Customer",
    "Document",
    "DocumentChunk",
    "DocumentChunkEmbedding",
    "Equipment",
    "Message",
    "OutboxEvent",
    "ServiceRecord",
    "Technician",
    "TechnicianAssignment",
    "User",
    "WebhookEvent",
    "WorkOrder",
    "WorkOrderProposal",
    "WorkflowRun",
]
