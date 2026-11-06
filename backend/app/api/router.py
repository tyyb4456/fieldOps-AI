from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import (
    admin,
    auth,
    complaints,
    customers,
    equipment,
    health,
    users,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(customers.router)
api_router.include_router(equipment.router)
api_router.include_router(complaints.router)
api_router.include_router(admin.router)
