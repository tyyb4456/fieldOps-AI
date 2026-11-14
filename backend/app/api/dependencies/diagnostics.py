from __future__ import annotations

from app.services.diagnostics.diagnostics import DiagnosticService
from app.services.workflows.factories import build_diagnostic_service


def get_diagnostic_service() -> DiagnosticService:
    """Construct the diagnostic service from application settings.

    The chat model factory and agent are resolved per request so the provider is
    only initialized when an investigation actually runs, and so tests can
    override this dependency without touching global state.
    """

    return build_diagnostic_service()
