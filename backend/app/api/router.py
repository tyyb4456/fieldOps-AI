from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import (
    admin,
    assignments,
    auth,
    complaints,
    customers,
    equipment,
    health,
    service_records,
    users,
    work_orders,
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
