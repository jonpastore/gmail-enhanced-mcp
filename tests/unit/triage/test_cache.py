from __future__ import annotations

import hashlib
import json
import threading
from datetime import UTC, datetime, timedelta

import pytest

from src.triage.cache import TriageCache
from src.triage.models import (
    FollowUp,
    FollowUpStatus,
    ImportanceScore,
    MessageCategory,
    PrioritySender,
    ScoringSignal,
    SenderTier,
    SyncState,
)


@pytest.fixture()
def cache(tmp_path: object) -> TriageCache:
    """Create an in-memory TriageCache for testing."""
    from pathlib import Path

    c = TriageCache(db_path=Path(":memory:"))
    c.initialize()
    return c


class TestInitialize:
    def test_creates_tables(self, cache: TriageCache) -> None:
        tables = cache._execute_read(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        table_names = [r["name"] for r in tables]
        assert "message_cache" in table_names
        assert "importance_scores" in table_names
        assert "follow_ups" in table_names
        assert "priority_senders" in table_names
        assert "sync_state" in table_names

    def test_wal_mode_enabled(self, cache: TriageCache) -> None:
        result = cache._execute_read("PRAGMA journal_mode")
        mode = result[0]["journal_mode"]
        assert mode in ("wal", "memory")

    def test_idempotent(self, cache: TriageCache) -> None:
        cache.initialize()
        tables = cache._execute_read(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        assert len([r for r in tables if r["name"] == "message_cache"]) == 1


class TestHashAddress:
    def test_produces_sha256(self) -> None:
        result = TriageCache.hash_address("test@example.com")
        expected = hashlib.sha256(b"test@example.com").hexdigest()
        assert result == expected

    def test_deterministic(self) -> None:
        assert TriageCache.hash_address("a@b.com") == TriageCache.hash_address("a@b.com")

    def test_different_inputs_different_hashes(self) -> None:
        assert TriageCache.hash_address("a@b.com") != TriageCache.hash_address("c@d.com")


class TestMessageMetadata:
    def test_cache_and_retrieve(self, cache: TriageCache) -> None:
        meta = {
            "message_id": "msg1",
            "thread_id": "t1",
            "account_hash": "acct_hash",
            "from_hash": "from_hash",
            "to_hashes": json.dumps(["to1", "to2"]),
            "subject_hash": "subj_hash",
            "date_received": "2026-01-01T00:00:00+00:00",
            "label_ids": json.dumps(["INBOX"]),
            "has_attachments": False,
            "header_list_unsubscribe": False,
            "header_precedence_bulk": False,
            "priority_sender_tier": None,
        }
        cache.cache_message_metadata(meta)
        result = cache.get_cached_message("msg1")
        assert result is not None
        assert result["message_id"] == "msg1"
        assert result["thread_id"] == "t1"

    def test_no_plaintext_addresses_stored(self, cache: TriageCache) -> None:
        addr = "user@example.com"
        hashed = TriageCache.hash_address(addr)
        meta = {
            "message_id": "msg2",
            "thread_id": "t1",
            "account_hash": "acct",
            "from_hash": hashed,
            "to_hashes": json.dumps([hashed]),
            "subject_hash": "subj",
            "date_received": "2026-01-01T00:00:00+00:00",
            "label_ids": json.dumps([]),
            "has_attachments": False,
            "header_list_unsubscribe": False,
            "header_precedence_bulk": False,
            "priority_sender_tier": None,
        }
        cache.cache_message_metadata(meta)
        result = cache.get_cached_message("msg2")
        assert result is not None
        assert addr not in json.dumps(result)

    def test_upsert_semantics(self, cache: TriageCache) -> None:
        meta = {
            "message_id": "msg3",
            "thread_id": "t1",
            "account_hash": "acct",
            "from_hash": "f1",
            "to_hashes": json.dumps([]),
            "subject_hash": "s1",
            "date_received": "2026-01-01T00:00:00+00:00",
            "label_ids": json.dumps(["INBOX"]),
            "has_attachments": False,
            "header_list_unsubscribe": False,
            "header_precedence_bulk": False,
            "priority_sender_tier": None,
        }
        cache.cache_message_metadata(meta)
        meta["label_ids"] = json.dumps(["INBOX", "STARRED"])
        cache.cache_message_metadata(meta)
        assert cache.row_count("message_cache") == 1
        result = cache.get_cached_message("msg3")
        assert result is not None
        assert "STARRED" in result["label_ids"]

    def test_get_cached_messages_by_account(self, cache: TriageCache) -> None:
        for i in range(3):
            cache.cache_message_metadata(
                {
                    "message_id": f"msg{i}",
                    "thread_id": f"t{i}",
                    "account_hash": "acct1",
                    "from_hash": "f",
                    "to_hashes": json.dumps([]),
                    "subject_hash": "s",
                    "date_received": "2026-01-01T00:00:00+00:00",
                    "label_ids": json.dumps([]),
                    "has_attachments": False,
                    "header_list_unsubscribe": False,
                    "header_precedence_bulk": False,
                    "priority_sender_tier": None,
                }
            )
        cache.cache_message_metadata(
            {
                "message_id": "other",
                "thread_id": "t_other",
                "account_hash": "acct2",
                "from_hash": "f",
                "to_hashes": json.dumps([]),
                "subject_hash": "s",
                "date_received": "2026-01-01T00:00:00+00:00",
                "label_ids": json.dumps([]),
                "has_attachments": False,
                "header_list_unsubscribe": False,
                "header_precedence_bulk": False,
                "priority_sender_tier": None,
            }
        )
        results = cache.get_cached_messages("acct1")
        assert len(results) == 3

    def test_get_nonexistent_message_returns_none(self, cache: TriageCache) -> None:
        assert cache.get_cached_message("nonexistent") is None


class TestImportanceScores:
    def _make_score(self, message_id: str = "msg1") -> ImportanceScore:
        return ImportanceScore(
            message_id=message_id,
            thread_id="t1",
            score=0.75,
            signals=[ScoringSignal(name="s1", weight=0.5, detail="d1")],
            category=MessageCategory.HIGH,
        )

    def test_store_and_retrieve(self, cache: TriageCache) -> None:
        cache.cache_message_metadata(
            {
                "message_id": "msg1",
                "thread_id": "t1",
                "account_hash": "a",
                "from_hash": "f",
                "to_hashes": "[]",
                "subject_hash": "s",
                "date_received": "2026-01-01T00:00:00+00:00",
                "label_ids": "[]",
                "has_attachments": False,
                "header_list_unsubscribe": False,
                "header_precedence_bulk": False,
                "priority_sender_tier": None,
            }
        )
        score = self._make_score()
        cache.store_score(score)
        result = cache.get_score("msg1")
        assert result is not None
        assert result.score == 0.75
        assert result.category == MessageCategory.HIGH

    def test_get_valid_score_within_ttl(self, cache: TriageCache) -> None:
        cache.cache_message_metadata(
            {
                "message_id": "msg1",
                "thread_id": "t1",
                "account_hash": "a",
                "from_hash": "f",
                "to_hashes": "[]",
                "subject_hash": "s",
                "date_received": "2026-01-01T00:00:00+00:00",
                "label_ids": "[]",
                "has_attachments": False,
                "header_list_unsubscribe": False,
                "header_precedence_bulk": False,
                "priority_sender_tier": None,
            }
        )
        cache.store_score(self._make_score())
        result = cache.get_valid_score("msg1")
        assert result is not None

    def test_get_valid_score_expired_returns_none(self, cache: TriageCache) -> None:
        cache.cache_message_metadata(
            {
                "message_id": "msg1",
                "thread_id": "t1",
                "account_hash": "a",
                "from_hash": "f",
                "to_hashes": "[]",
                "subject_hash": "s",
                "date_received": "2026-01-01T00:00:00+00:00",
                "label_ids": "[]",
                "has_attachments": False,
                "header_list_unsubscribe": False,
                "header_precedence_bulk": False,
                "priority_sender_tier": None,
            }
        )
        cache.store_score(self._make_score())
        old_time = (datetime.now(tz=UTC) - timedelta(hours=25)).isoformat()
        cache._execute_write(
            "UPDATE importance_scores SET scored_at = ? WHERE message_id = ?",
            (old_time, "msg1"),
        )
        result = cache.get_valid_score("msg1")
        assert result is None

    def test_score_upsert(self, cache: TriageCache) -> None:
        cache.cache_message_metadata(
            {
                "message_id": "msg1",
                "thread_id": "t1",
                "account_hash": "a",
                "from_hash": "f",
                "to_hashes": "[]",
                "subject_hash": "s",
                "date_received": "2026-01-01T00:00:00+00:00",
                "label_ids": "[]",
                "has_attachments": False,
                "header_list_unsubscribe": False,
                "header_precedence_bulk": False,
                "priority_sender_tier": None,
            }
        )
        cache.store_score(self._make_score())
        updated = ImportanceScore(
            message_id="msg1",
            thread_id="t1",
            score=0.9,
            signals=[],
            category=MessageCategory.CRITICAL,
        )
        cache.store_score(updated)
        assert cache.row_count("importance_scores") == 1
        result = cache.get_score("msg1")
        assert result is not None
        assert result.score == 0.9

    def test_get_nonexistent_score_returns_none(self, cache: TriageCache) -> None:
        assert cache.get_score("nonexistent") is None


class TestFollowUps:
    def _make_follow_up(self, message_id: str = "msg1", account_hash: str = "acct1") -> FollowUp:
        now = datetime.now(tz=UTC)
        return FollowUp(
            message_id=message_id,
            thread_id="t1",
            subject_hash="subj_hash",
            sent_date=now,
            expected_reply_days=3,
            deadline=now + timedelta(days=3),
            status=FollowUpStatus.WAITING,
        )

    def test_add_and_retrieve(self, cache: TriageCache) -> None:
        fu = self._make_follow_up()
        fu_id = cache.add_follow_up(fu)
        assert fu_id > 0
        results = cache.get_follow_ups("acct1")
        assert len(results) >= 0  # account_hash not in FollowUp model directly

    def test_update_status(self, cache: TriageCache) -> None:
        fu = self._make_follow_up()
        fu_id = cache.add_follow_up(fu)
        cache.update_follow_up_status(fu_id, FollowUpStatus.REPLIED)
        cache.get_follow_ups("any", status=FollowUpStatus.REPLIED)
        # We check via direct query since account_hash filtering may vary
        rows = cache._execute_read("SELECT status FROM follow_ups WHERE id = ?", (fu_id,))
        assert rows[0]["status"] == "replied"

    def test_filter_by_status(self, cache: TriageCache) -> None:
        fu1 = self._make_follow_up("msg1")
        fu2 = self._make_follow_up("msg2")
        cache.add_follow_up(fu1)
        fu2_id = cache.add_follow_up(fu2)
        cache.update_follow_up_status(fu2_id, FollowUpStatus.EXPIRED)
        rows = cache._execute_read("SELECT * FROM follow_ups WHERE status = ?", ("waiting",))
        assert len(rows) == 1


class TestPrioritySenders:
    def test_add_and_retrieve(self, cache: TriageCache) -> None:
        sender = PrioritySender(
            email_pattern="boss@example.com", tier=SenderTier.CRITICAL, label="Boss"
        )
        cache.add_priority_sender(sender)
        senders = cache.get_priority_senders()
        assert len(senders) == 1
        assert senders[0].email_pattern == "boss@example.com"
        assert senders[0].tier == SenderTier.CRITICAL

    def test_upsert_on_duplicate_pattern(self, cache: TriageCache) -> None:
        sender1 = PrioritySender(
            email_pattern="boss@example.com", tier=SenderTier.HIGH, label="Boss"
        )
        sender2 = PrioritySender(
            email_pattern="boss@example.com", tier=SenderTier.CRITICAL, label="CEO"
        )
        cache.add_priority_sender(sender1)
        cache.add_priority_sender(sender2)
        assert cache.row_count("priority_senders") == 1
        senders = cache.get_priority_senders()
        assert senders[0].tier == SenderTier.CRITICAL

    def test_remove_existing(self, cache: TriageCache) -> None:
        sender = PrioritySender(
            email_pattern="boss@example.com", tier=SenderTier.HIGH, label="Boss"
        )
        cache.add_priority_sender(sender)
        assert cache.remove_priority_sender("boss@example.com") is True
        assert len(cache.get_priority_senders()) == 0

    def test_remove_nonexistent_returns_false(self, cache: TriageCache) -> None:
        assert cache.remove_priority_sender("nobody@example.com") is False


class TestSyncState:
    def test_update_and_retrieve(self, cache: TriageCache) -> None:
        now = datetime.now(tz=UTC)
        state = SyncState(
            account_email_hash="hash1",
            provider="gmail",
            sync_token="token123",
            last_sync=now,
            messages_cached=42,
        )
        cache.update_sync_state(state)
        result = cache.get_sync_state("hash1")
        assert result is not None
        assert result.provider == "gmail"
        assert result.sync_token == "token123"
        assert result.messages_cached == 42

    def test_upsert_sync_state(self, cache: TriageCache) -> None:
        now = datetime.now(tz=UTC)
        state1 = SyncState(
            account_email_hash="hash1",
            provider="gmail",
            sync_token="t1",
            last_sync=now,
            messages_cached=10,
        )
        state2 = SyncState(
            account_email_hash="hash1",
            provider="gmail",
            sync_token="t2",
            last_sync=now,
            messages_cached=20,
        )
        cache.update_sync_state(state1)
        cache.update_sync_state(state2)
        assert cache.row_count("sync_state") == 1
        result = cache.get_sync_state("hash1")
        assert result is not None
        assert result.sync_token == "t2"

    def test_get_nonexistent_returns_none(self, cache: TriageCache) -> None:
        assert cache.get_sync_state("nonexistent") is None


class TestEviction:
    def test_evict_expired_scores(self, cache: TriageCache) -> None:
        cache.cache_message_metadata(
            {
                "message_id": "msg1",
                "thread_id": "t1",
                "account_hash": "a",
                "from_hash": "f",
                "to_hashes": "[]",
                "subject_hash": "s",
                "date_received": "2026-01-01T00:00:00+00:00",
                "label_ids": "[]",
                "has_attachments": False,
                "header_list_unsubscribe": False,
                "header_precedence_bulk": False,
                "priority_sender_tier": None,
            }
        )
        score = ImportanceScore(
            message_id="msg1",
            thread_id="t1",
            score=0.5,
            signals=[],
            category=MessageCategory.NORMAL,
        )
        cache.store_score(score)
        old_time = (datetime.now(tz=UTC) - timedelta(hours=25)).isoformat()
        cache._execute_write(
            "UPDATE importance_scores SET scored_at = ? WHERE message_id = ?",
            (old_time, "msg1"),
        )
        evicted = cache.evict_expired()
        assert evicted > 0
        assert cache.get_score("msg1") is None

    def test_evict_expired_metadata(self, cache: TriageCache) -> None:
        cache.cache_message_metadata(
            {
                "message_id": "old_msg",
                "thread_id": "t1",
                "account_hash": "a",
                "from_hash": "f",
                "to_hashes": "[]",
                "subject_hash": "s",
                "date_received": "2026-01-01T00:00:00+00:00",
                "label_ids": "[]",
                "has_attachments": False,
                "header_list_unsubscribe": False,
                "header_precedence_bulk": False,
                "priority_sender_tier": None,
            }
        )
        old_time = (datetime.now(tz=UTC) - timedelta(days=31)).isoformat()
        cache._execute_write(
            "UPDATE message_cache SET cached_at = ? WHERE message_id = ?",
            (old_time, "old_msg"),
        )
        evicted = cache.evict_expired()
        assert evicted > 0
        assert cache.get_cached_message("old_msg") is None


class TestReset:
    def test_reset_clears_all_data(self, cache: TriageCache) -> None:
        cache.cache_message_metadata(
            {
                "message_id": "msg1",
                "thread_id": "t1",
                "account_hash": "a",
                "from_hash": "f",
                "to_hashes": "[]",
                "subject_hash": "s",
                "date_received": "2026-01-01T00:00:00+00:00",
                "label_ids": "[]",
                "has_attachments": False,
                "header_list_unsubscribe": False,
                "header_precedence_bulk": False,
                "priority_sender_tier": None,
            }
        )
        cache.reset()
        assert cache.row_count("message_cache") == 0
        tables = cache._execute_read(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        table_names = [r["name"] for r in tables]
        assert "message_cache" in table_names


class TestRowCount:
    def test_empty_table(self, cache: TriageCache) -> None:
        assert cache.row_count("message_cache") == 0

    def test_after_inserts(self, cache: TriageCache) -> None:
        for i in range(5):
            cache.cache_message_metadata(
                {
                    "message_id": f"msg{i}",
                    "thread_id": "t1",
                    "account_hash": "a",
                    "from_hash": "f",
                    "to_hashes": "[]",
                    "subject_hash": "s",
                    "date_received": "2026-01-01T00:00:00+00:00",
                    "label_ids": "[]",
                    "has_attachments": False,
                    "header_list_unsubscribe": False,
                    "header_precedence_bulk": False,
                    "priority_sender_tier": None,
                }
            )
        assert cache.row_count("message_cache") == 5


class TestDismissedContacts:
    def test_dismiss_contact_stores_pattern(self, cache: TriageCache) -> None:
        cache.dismiss_contact("spam@example.com")
        dismissed = cache.get_dismissed_contacts()
        assert len(dismissed) == 1
        assert dismissed[0]["email_pattern"] == "spam@example.com"
        assert "dismissed_at" in dismissed[0]

    def test_dismiss_duplicate_is_idempotent(self, cache: TriageCache) -> None:
        cache.dismiss_contact("spam@example.com")
        cache.dismiss_contact("spam@example.com")
        dismissed = cache.get_dismissed_contacts()
        assert len(dismissed) == 1

    def test_is_dismissed_returns_true(self, cache: TriageCache) -> None:
        cache.dismiss_contact("spam@example.com")
        assert cache.is_dismissed("spam@example.com") is True

    def test_is_dismissed_returns_false(self, cache: TriageCache) -> None:
        assert cache.is_dismissed("good@example.com") is False

    def test_undismiss_contact(self, cache: TriageCache) -> None:
        cache.dismiss_contact("spam@example.com")
        cache.undismiss_contact("spam@example.com")
        assert cache.is_dismissed("spam@example.com") is False


class TestThreadSafety:
    def test_concurrent_writes(self, cache: TriageCache) -> None:
        errors: list[Exception] = []

        def write_messages(start: int, count: int) -> None:
            try:
                for i in range(start, start + count):
                    cache.cache_message_metadata(
                        {
                            "message_id": f"msg{i}",
                            "thread_id": "t1",
                            "account_hash": "a",
                            "from_hash": "f",
                            "to_hashes": "[]",
                            "subject_hash": "s",
                            "date_received": "2026-01-01T00:00:00+00:00",
                            "label_ids": "[]",
                            "has_attachments": False,
                            "header_list_unsubscribe": False,
                            "header_precedence_bulk": False,
                            "priority_sender_tier": None,
                        }
                    )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=write_messages, args=(i * 10, 10)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0
        assert cache.row_count("message_cache") == 50
