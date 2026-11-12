from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import admin, health
from app.api.routes.accounts import auth, users
from app.api.routes.assignments import assignments
from app.api.routes.complaints import complaints
from app.api.routes.customers import customers
from app.api.routes.diagnostics import diagnostics
from app.api.routes.documents import documents
from app.api.routes.equipment import equipment
from app.api.routes.rag import retrieval
from app.api.routes.work_orders import (
    completion_reports,
    service_records,
    work_order_proposals,
    work_orders,
)
from app.api.routes.workflow_runs import workflow_runs

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(customers.router)
api_router.include_router(equipment.router)
api_router.include_router(complaints.router)
api_router.include_router(admin.router)
api_router.include_router(work_orders.router)
api_router.include_router(work_order_proposals.router)
api_router.include_router(assignments.router)
api_router.include_router(service_records.router)
api_router.include_router(completion_reports.router)
api_router.include_router(documents.router)
api_router.include_router(retrieval.router)
api_router.include_router(diagnostics.router)
api_router.include_router(workflow_runs.router)
