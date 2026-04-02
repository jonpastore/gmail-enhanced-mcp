from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .email_client import EmailClient
    from .triage.cache import TriageCache


@dataclass
class HandlerContext:
    """Unified context passed to all tool handlers."""

    client: EmailClient
    cache: TriageCache | None = None
    calendar_ctx: Any | None = None
