"""Pydantic models and base exception for the triage subsystem."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class GmailMCPError(Exception):
    """Base exception for gmail-enhanced-mcp operations."""


class MessageCategory(StrEnum):
    """Category assigned to a message based on importance score."""

    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"
    JUNK = "junk"


class ScoringSignal(BaseModel):
    """A single signal contributing to an importance score."""

    name: str
    weight: float
    detail: str


class ImportanceScore(BaseModel):
    """Computed importance score for a single message."""

    message_id: str
    thread_id: str
    score: float
    signals: list[ScoringSignal]
    category: MessageCategory


class FollowUpStatus(StrEnum):
    """Status of a follow-up tracker."""

    WAITING = "waiting"
    REPLIED = "replied"
    EXPIRED = "expired"
    DISMISSED = "dismissed"


class FollowUp(BaseModel):
    """Tracks a sent message awaiting a reply."""

    message_id: str
    thread_id: str
    subject_hash: str
    sent_date: datetime
    expected_reply_days: int
    deadline: datetime | None
    status: FollowUpStatus


class SenderTier(StrEnum):
    """Priority tier for a known sender."""

    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"


class PrioritySender(BaseModel):
    """A sender configured with a priority tier."""

    email_pattern: str
    tier: SenderTier
    label: str


class JunkSignal(BaseModel):
    """Junk detection result for a message."""

    message_id: str
    is_junk: bool
    confidence: float
    reasons: list[str]


class AutoSortProposal(BaseModel):
    """A proposed label assignment for a thread."""

    thread_id: str
    proposed_label: str
    reason: str
    confidence: float


class TriageResult(BaseModel):
    """Combined triage output for a batch of messages."""

    scores: list[ImportanceScore]
    junk_flags: list[JunkSignal]
    sort_proposals: list[AutoSortProposal]


class SyncState(BaseModel):
    """Tracks sync progress for an account."""

    account_email_hash: str
    provider: str
    sync_token: str | None
    last_sync: datetime
    messages_cached: int
