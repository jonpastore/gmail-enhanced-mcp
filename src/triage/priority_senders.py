"""Priority sender management for email triage."""

from __future__ import annotations

from src.triage.cache import TriageCache
from src.triage.models import PrioritySender, SenderTier


class PrioritySenderManager:
    """Manages priority sender patterns with exact and domain glob matching."""

    def __init__(self, cache: TriageCache) -> None:
        """Initialize with a TriageCache for persistence.

        Args:
            cache: TriageCache instance for CRUD operations.
        """
        self._cache = cache

    def match(self, email_address: str) -> PrioritySender | None:
        """Match an email address against priority sender patterns.

        Supports exact match and *@domain glob. Exact matches take
        priority over glob matches.

        Args:
            email_address: Email address to match.

        Returns:
            Matching PrioritySender or None.
        """
        senders = self._cache.get_priority_senders()
        addr_lower = email_address.lower()
        domain = addr_lower.split("@", 1)[1] if "@" in addr_lower else ""

        exact_match: PrioritySender | None = None
        glob_match: PrioritySender | None = None

        for ps in senders:
            pattern = ps.email_pattern.lower()
            if pattern == addr_lower:
                exact_match = ps
                break
            if pattern.startswith("*@") and domain == pattern[2:]:
                glob_match = ps

        return exact_match if exact_match is not None else glob_match

    def add(self, pattern: str, tier: SenderTier, label: str) -> None:
        """Add a priority sender pattern.

        Args:
            pattern: Email address or *@domain glob.
            tier: Priority tier for this sender.
            label: Human-readable label.
        """
        sender = PrioritySender(email_pattern=pattern, tier=tier, label=label)
        self._cache.add_priority_sender(sender)

    def remove(self, pattern: str) -> bool:
        """Remove a priority sender by pattern.

        Args:
            pattern: The exact pattern string to remove.

        Returns:
            True if a sender was removed, False otherwise.
        """
        return self._cache.remove_priority_sender(pattern)

    def list_all(self) -> list[PrioritySender]:
        """List all priority senders.

        Returns:
            List of all configured PrioritySender entries.
        """
        return self._cache.get_priority_senders()
