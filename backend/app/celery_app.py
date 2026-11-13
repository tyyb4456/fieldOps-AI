from __future__ import annotations

from celery import Celery  # type: ignore[import-untyped]

from app.core.config import settings

celery_app = Celery(
    "fieldops",
    broker=settings.effective_celery_broker_url,
    backend=settings.effective_celery_result_backend,
)

celery_app.conf.update(
    accept_content=["json"],
    broker_connection_retry_on_startup=True,
    enable_utc=True,
    imports=("app.tasks.documents",),
    result_expires=60 * 60 * 24,
    result_serializer="json",
    task_acks_late=True,
    task_always_eager=settings.celery_task_always_eager,
    task_default_queue="fieldops",
    task_eager_propagates=settings.celery_task_eager_propagates,
    task_reject_on_worker_lost=True,
    task_serializer="json",
    task_soft_time_limit=settings.celery_task_soft_time_limit_seconds,
    task_time_limit=settings.celery_task_time_limit_seconds,
    task_track_started=True,
    timezone="UTC",
    worker_prefetch_multiplier=1,
)

__all__ = ["celery_app"]
