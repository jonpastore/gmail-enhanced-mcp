"""Triage subsystem for email importance scoring and follow-up tracking."""

from __future__ import annotations

from .cache import TriageCache
from .engine import ImportanceScorer, JunkDetector
from .models import (
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
from .priority_senders import PrioritySenderManager
from .tracker import DeadlineExtractor, FollowUpTracker

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
