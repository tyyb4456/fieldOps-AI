from __future__ import annotations

from app.core.config import settings
from app.services.storage import DocumentStorage, build_document_storage


def get_document_storage() -> DocumentStorage:
    return build_document_storage(settings)
