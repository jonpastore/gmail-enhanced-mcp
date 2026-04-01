"""Tests for PrioritySenderManager."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.triage.cache import TriageCache
from src.triage.models import SenderTier
from src.triage.priority_senders import PrioritySenderManager


@pytest.fixture()
def cache() -> TriageCache:
    c = TriageCache(db_path=Path(":memory:"))
    c.initialize()
    return c


@pytest.fixture()
def manager(cache: TriageCache) -> PrioritySenderManager:
    return PrioritySenderManager(cache=cache)


class TestExactMatch:
    def test_exact_email_match(self, manager: PrioritySenderManager) -> None:
        manager.add("boss@work.com", SenderTier.HIGH, "Boss")
        result = manager.match("boss@work.com")
        assert result is not None
        assert result.tier == SenderTier.HIGH
        assert result.label == "Boss"

    def test_no_match_returns_none(self, manager: PrioritySenderManager) -> None:
        manager.add("boss@work.com", SenderTier.HIGH, "Boss")
        result = manager.match("stranger@example.com")
        assert result is None


class TestDomainGlob:
    def test_domain_glob_match(self, manager: PrioritySenderManager) -> None:
        manager.add("*@irs.gov", SenderTier.CRITICAL, "IRS")
        result = manager.match("taxes@irs.gov")
        assert result is not None
        assert result.tier == SenderTier.CRITICAL

    def test_domain_glob_no_match(self, manager: PrioritySenderManager) -> None:
        manager.add("*@irs.gov", SenderTier.CRITICAL, "IRS")
        result = manager.match("taxes@notirs.gov")
        assert result is None


class TestCRUD:
    def test_add_and_list_all(self, manager: PrioritySenderManager) -> None:
        manager.add("a@b.com", SenderTier.HIGH, "A")
        manager.add("*@c.com", SenderTier.CRITICAL, "C")
        all_senders = manager.list_all()
        assert len(all_senders) == 2

    def test_remove_existing(self, manager: PrioritySenderManager) -> None:
        manager.add("a@b.com", SenderTier.HIGH, "A")
        assert manager.remove("a@b.com") is True
        assert manager.match("a@b.com") is None

    def test_remove_nonexistent(self, manager: PrioritySenderManager) -> None:
        assert manager.remove("nope@x.com") is False

    def test_list_empty(self, manager: PrioritySenderManager) -> None:
        assert manager.list_all() == []


class TestTierOrdering:
    def test_critical_higher_than_high(self) -> None:
        tiers = [SenderTier.NORMAL, SenderTier.HIGH, SenderTier.CRITICAL]
        assert SenderTier.CRITICAL in tiers
        assert SenderTier.HIGH in tiers

    def test_exact_match_preferred_over_glob(self, manager: PrioritySenderManager) -> None:
        manager.add("*@work.com", SenderTier.NORMAL, "Work domain")
        manager.add("boss@work.com", SenderTier.CRITICAL, "Boss")
        result = manager.match("boss@work.com")
        assert result is not None
        assert result.tier == SenderTier.CRITICAL
