from __future__ import annotations

from datetime import UTC, datetime

import pytest

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


class TestGmailMCPError:
    def test_is_exception_subclass(self) -> None:
        assert issubclass(GmailMCPError, Exception)

    def test_can_raise_and_catch(self) -> None:
        with pytest.raises(GmailMCPError, match="test error"):
            raise GmailMCPError("test error")


class TestMessageCategory:
    def test_all_values(self) -> None:
        assert MessageCategory.CRITICAL == "critical"
        assert MessageCategory.HIGH == "high"
        assert MessageCategory.NORMAL == "normal"
        assert MessageCategory.LOW == "low"
        assert MessageCategory.JUNK == "junk"

    def test_is_str_enum(self) -> None:
        assert isinstance(MessageCategory.CRITICAL, str)


class TestFollowUpStatus:
    def test_all_values(self) -> None:
        assert FollowUpStatus.WAITING == "waiting"
        assert FollowUpStatus.REPLIED == "replied"
        assert FollowUpStatus.EXPIRED == "expired"
        assert FollowUpStatus.DISMISSED == "dismissed"


class TestSenderTier:
    def test_all_values(self) -> None:
        assert SenderTier.CRITICAL == "critical"
        assert SenderTier.HIGH == "high"
        assert SenderTier.NORMAL == "normal"


class TestScoringSignal:
    def test_creation(self) -> None:
        signal = ScoringSignal(name="direct_recipient", weight=0.15, detail="To: user")
        assert signal.name == "direct_recipient"
        assert signal.weight == 0.15
        assert signal.detail == "To: user"


class TestImportanceScore:
    def test_creation(self) -> None:
        score = ImportanceScore(
            message_id="msg1",
            thread_id="thread1",
            score=0.75,
            signals=[ScoringSignal(name="s1", weight=0.5, detail="d1")],
            category=MessageCategory.HIGH,
        )
        assert score.score == 0.75
        assert score.category == MessageCategory.HIGH
        assert len(score.signals) == 1

    def test_invalid_category_raises(self) -> None:
        with pytest.raises(ValueError):
            ImportanceScore(
                message_id="msg1",
                thread_id="t1",
                score=0.5,
                signals=[],
                category="invalid",  # type: ignore[arg-type]
            )


class TestFollowUp:
    def test_creation(self) -> None:
        now = datetime.now(tz=UTC)
        fu = FollowUp(
            message_id="msg1",
            thread_id="t1",
            subject_hash="abc123",
            sent_date=now,
            expected_reply_days=3,
            deadline=None,
            status=FollowUpStatus.WAITING,
        )
        assert fu.status == FollowUpStatus.WAITING
        assert fu.deadline is None


class TestPrioritySender:
    def test_creation(self) -> None:
        ps = PrioritySender(
            email_pattern="boss@example.com", tier=SenderTier.CRITICAL, label="Boss"
        )
        assert ps.tier == SenderTier.CRITICAL


class TestJunkSignal:
    def test_creation(self) -> None:
        js = JunkSignal(message_id="msg1", is_junk=True, confidence=0.95, reasons=["bulk header"])
        assert js.is_junk is True
        assert len(js.reasons) == 1


class TestAutoSortProposal:
    def test_creation(self) -> None:
        asp = AutoSortProposal(
            thread_id="t1", proposed_label="Finance", reason="Invoice detected", confidence=0.8
        )
        assert asp.proposed_label == "Finance"


class TestTriageResult:
    def test_creation(self) -> None:
        result = TriageResult(scores=[], junk_flags=[], sort_proposals=[])
        assert result.scores == []


class TestSyncState:
    def test_creation(self) -> None:
        now = datetime.now(tz=UTC)
        state = SyncState(
            account_email_hash="hash123",
            provider="gmail",
            sync_token=None,
            last_sync=now,
            messages_cached=0,
        )
        assert state.provider == "gmail"
        assert state.sync_token is None
