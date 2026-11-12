from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import (
    admin,
    assignments,
    auth,
    complaints,
    completion_reports,
    customers,
    diagnostics,
    documents,
    equipment,
    health,
    retrieval,
    service_records,
    users,
    work_orders,
    workflow_runs,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(customers.router)
api_router.include_router(equipment.router)
api_router.include_router(complaints.router)
api_router.include_router(admin.router)
api_router.include_router(work_orders.router)
api_router.include_router(assignments.router)
api_router.include_router(service_records.router)
api_router.include_router(completion_reports.router)
api_router.include_router(documents.router)
api_router.include_router(retrieval.router)
api_router.include_router(diagnostics.router)
api_router.include_router(workflow_runs.router)
