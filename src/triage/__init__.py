"""Triage subsystem for email importance scoring and follow-up tracking."""

from __future__ import annotations

from src.triage.cache import TriageCache
from src.triage.engine import ImportanceScorer, JunkDetector
from src.triage.models import (
    AutoSortProposal,
    FollowUp,
    FollowUpStatus,
    GmailMCPError,
    ImportanceScore,
    JunkSignal,
    MessageCategory,
    PrioritySender,
    ScoringSignal,
    SenderTier,
    SyncState,
    TriageResult,
)
from src.triage.priority_senders import PrioritySenderManager
from src.triage.tracker import DeadlineExtractor, FollowUpTracker

__all__ = [
    "AutoSortProposal",
    "DeadlineExtractor",
    "FollowUp",
    "FollowUpStatus",
    "FollowUpTracker",
    "GmailMCPError",
    "ImportanceScore",
    "ImportanceScorer",
    "JunkDetector",
    "JunkSignal",
    "MessageCategory",
    "PrioritySender",
    "PrioritySenderManager",
    "ScoringSignal",
    "SenderTier",
    "SyncState",
    "TriageCache",
    "TriageResult",
]
