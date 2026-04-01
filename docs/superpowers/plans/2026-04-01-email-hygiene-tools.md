# Email Hygiene Tools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 6 Gmail-only MCP tools for email hygiene: trash, block, spam, contacts list, contacts import as priority senders, and unsubscribe link extraction.

**Architecture:** New methods on `GmailClient` (not on `EmailClient` ABC — these are Gmail/Google-specific). New tool handler file `src/tools/hygiene.py`. Tools registered in `src/tools/__init__.py` alongside existing tools. Provider guard rejects Outlook accounts with clear error.

**Tech Stack:** Google Gmail API v1 (`messages().trash()`, `messages().batchModify()`, `settings().filters().create()`), Google People API v1 (`people().connections().list()`), existing `PrioritySenderManager` for contacts import.

**Spec:** `docs/superpowers/specs/2026-04-01-email-hygiene-tools-design.md`

---

### Task 1: GmailClient — trash_messages and trash_by_query

**Files:**
- Modify: `src/gmail_client.py` (append after `history_sync` method, ~line 331)
- Test: `tests/unit/test_gmail_client.py`

- [ ] **Step 1: Write failing tests for trash_messages**

Add to `tests/unit/test_gmail_client.py`:

```python
class TestTrashMessages:
    def test_trashes_single_message(self) -> None:
        mock_svc = MagicMock()
        mock_svc.users().messages().trash().execute.return_value = {"id": "msg_001"}
        client = _make_client(mock_svc)
        result = client.trash_messages(["msg_001"])
        assert result["trashed_count"] == 1
        assert result["message_ids"] == ["msg_001"]

    def test_trashes_multiple_messages(self) -> None:
        mock_svc = MagicMock()
        mock_svc.users().messages().trash().execute.return_value = {"id": "msg_001"}
        client = _make_client(mock_svc)
        result = client.trash_messages(["msg_001", "msg_002", "msg_003"])
        assert result["trashed_count"] == 3

    def test_empty_list_returns_zero(self) -> None:
        client = _make_client()
        result = client.trash_messages([])
        assert result["trashed_count"] == 0
        assert result["message_ids"] == []


class TestTrashByQuery:
    def test_searches_and_trashes(self) -> None:
        mock_svc = MagicMock()
        mock_svc.users().messages().list().execute.return_value = {
            "messages": [{"id": "msg_001", "threadId": "t_001"}, {"id": "msg_002", "threadId": "t_002"}],
            "resultSizeEstimate": 2,
        }
        mock_svc.users().messages().trash().execute.return_value = {"id": "msg_001"}
        client = _make_client(mock_svc)
        result = client.trash_by_query("from:spam@example.com")
        assert result["trashed_count"] == 2

    def test_no_results_returns_zero(self) -> None:
        mock_svc = MagicMock()
        mock_svc.users().messages().list().execute.return_value = {
            "resultSizeEstimate": 0,
        }
        client = _make_client(mock_svc)
        result = client.trash_by_query("from:nobody@example.com")
        assert result["trashed_count"] == 0
        assert result["message_ids"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_gmail_client.py::TestTrashMessages -v && pytest tests/unit/test_gmail_client.py::TestTrashByQuery -v`
Expected: FAIL with `AttributeError: 'GmailClient' object has no attribute 'trash_messages'`

- [ ] **Step 3: Implement trash_messages and trash_by_query**

Add to `src/gmail_client.py` after the `history_sync` method:

```python
    def trash_messages(self, message_ids: list[str]) -> dict[str, Any]:
        """Move messages to trash by ID.

        Args:
            message_ids: List of message IDs to trash.

        Returns:
            Dict with trashed_count and message_ids.
        """
        if not message_ids:
            return {"trashed_count": 0, "message_ids": []}
        svc = self._get_service()
        trashed: list[str] = []
        for msg_id in message_ids:
            svc.users().messages().trash(userId="me", id=msg_id).execute()
            trashed.append(msg_id)
            logger.info(f"Trashed message: {msg_id}")
        return {"trashed_count": len(trashed), "message_ids": trashed}

    def trash_by_query(self, query: str, max_results: int = 500) -> dict[str, Any]:
        """Search for messages and trash all results.

        Args:
            query: Gmail search query.
            max_results: Maximum messages to trash.

        Returns:
            Dict with trashed_count and message_ids.
        """
        result = self.search_messages(q=query, max_results=max_results)
        messages = result["messages"]
        if not messages:
            return {"trashed_count": 0, "message_ids": []}
        ids = [m["id"] for m in messages]
        return self.trash_messages(ids)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_gmail_client.py::TestTrashMessages tests/unit/test_gmail_client.py::TestTrashByQuery -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/gmail_client.py tests/unit/test_gmail_client.py
git commit -m "feat: add trash_messages and trash_by_query to GmailClient"
```

---

### Task 2: GmailClient — create_block_filter

**Files:**
- Modify: `src/gmail_client.py`
- Test: `tests/unit/test_gmail_client.py`

- [ ] **Step 1: Write failing test**

```python
class TestCreateBlockFilter:
    def test_creates_filter_and_trashes_existing(self) -> None:
        mock_svc = MagicMock()
        mock_svc.users().settings().filters().create().execute.return_value = {
            "id": "filter_001",
        }
        mock_svc.users().messages().list().execute.return_value = {
            "messages": [{"id": "msg_001", "threadId": "t_001"}],
            "resultSizeEstimate": 1,
        }
        mock_svc.users().messages().trash().execute.return_value = {"id": "msg_001"}
        client = _make_client(mock_svc)
        result = client.create_block_filter("spam@example.com")
        assert result["filter_id"] == "filter_001"
        assert result["existing_trashed"] == 1

    def test_creates_filter_no_existing_messages(self) -> None:
        mock_svc = MagicMock()
        mock_svc.users().settings().filters().create().execute.return_value = {
            "id": "filter_002",
        }
        mock_svc.users().messages().list().execute.return_value = {
            "resultSizeEstimate": 0,
        }
        client = _make_client(mock_svc)
        result = client.create_block_filter("nobody@example.com")
        assert result["filter_id"] == "filter_002"
        assert result["existing_trashed"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_gmail_client.py::TestCreateBlockFilter -v`
Expected: FAIL

- [ ] **Step 3: Implement create_block_filter**

```python
    def create_block_filter(self, sender: str) -> dict[str, Any]:
        """Create a Gmail filter to auto-delete from sender and trash existing.

        Args:
            sender: Email address or domain to block.

        Returns:
            Dict with filter_id and existing_trashed count.
        """
        svc = self._get_service()
        filter_body = {
            "criteria": {"from": sender},
            "action": {
                "removeLabelIds": ["INBOX"],
                "addLabelIds": ["TRASH"],
            },
        }
        created = svc.users().settings().filters().create(
            userId="me", body=filter_body
        ).execute()
        filter_id = created.get("id", "")
        logger.info(f"Created block filter for {sender}: {filter_id}")
        trash_result = self.trash_by_query(f"from:{sender}")
        return {
            "filter_id": filter_id,
            "existing_trashed": trash_result["trashed_count"],
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_gmail_client.py::TestCreateBlockFilter -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/gmail_client.py tests/unit/test_gmail_client.py
git commit -m "feat: add create_block_filter to GmailClient"
```

---

### Task 3: GmailClient — report_spam

**Files:**
- Modify: `src/gmail_client.py`
- Test: `tests/unit/test_gmail_client.py`

- [ ] **Step 1: Write failing test**

```python
class TestReportSpam:
    def test_reports_messages_as_spam(self) -> None:
        mock_svc = MagicMock()
        mock_svc.users().messages().batchModify().execute.return_value = {}
        client = _make_client(mock_svc)
        result = client.report_spam(["msg_001", "msg_002"])
        assert result["reported_count"] == 2
        mock_svc.users().messages().batchModify.assert_called_once_with(
            userId="me",
            body={
                "ids": ["msg_001", "msg_002"],
                "addLabelIds": ["SPAM"],
                "removeLabelIds": ["INBOX"],
            },
        )

    def test_empty_list_returns_zero(self) -> None:
        client = _make_client()
        result = client.report_spam([])
        assert result["reported_count"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_gmail_client.py::TestReportSpam -v`
Expected: FAIL

- [ ] **Step 3: Implement report_spam**

```python
    def report_spam(self, message_ids: list[str]) -> dict[str, Any]:
        """Report messages as spam via batchModify.

        Args:
            message_ids: List of message IDs to report.

        Returns:
            Dict with reported_count.
        """
        if not message_ids:
            return {"reported_count": 0}
        svc = self._get_service()
        svc.users().messages().batchModify(
            userId="me",
            body={
                "ids": message_ids,
                "addLabelIds": ["SPAM"],
                "removeLabelIds": ["INBOX"],
            },
        ).execute()
        logger.info(f"Reported {len(message_ids)} messages as spam")
        return {"reported_count": len(message_ids)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_gmail_client.py::TestReportSpam -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/gmail_client.py tests/unit/test_gmail_client.py
git commit -m "feat: add report_spam to GmailClient"
```

---

### Task 4: GmailClient — get_contacts

**Files:**
- Modify: `src/gmail_client.py`
- Test: `tests/unit/test_gmail_client.py`

- [ ] **Step 1: Write failing test**

```python
class TestGetContacts:
    def test_returns_contacts_with_emails(self) -> None:
        mock_svc = MagicMock()
        client = _make_client(mock_svc)
        # Mock People API service separately
        mock_people = MagicMock()
        mock_people.people().connections().list().execute.return_value = {
            "connections": [
                {
                    "names": [{"displayName": "Alice Smith"}],
                    "emailAddresses": [{"value": "alice@example.com"}],
                },
                {
                    "names": [{"displayName": "Bob Jones"}],
                    "emailAddresses": [
                        {"value": "bob@example.com"},
                        {"value": "bob@work.com"},
                    ],
                },
                {
                    "names": [{"displayName": "No Email"}],
                },
            ],
        }
        with patch("src.gmail_client.build", return_value=mock_people):
            result = client.get_contacts(max_results=100)
        assert len(result) == 2
        assert result[0]["name"] == "Alice Smith"
        assert result[0]["emails"] == ["alice@example.com"]
        assert result[1]["emails"] == ["bob@example.com", "bob@work.com"]

    def test_paginates_through_all_contacts(self) -> None:
        mock_svc = MagicMock()
        client = _make_client(mock_svc)
        mock_people = MagicMock()
        page1 = {
            "connections": [
                {"names": [{"displayName": "Alice"}], "emailAddresses": [{"value": "alice@test.com"}]},
            ],
            "nextPageToken": "page2",
        }
        page2 = {
            "connections": [
                {"names": [{"displayName": "Bob"}], "emailAddresses": [{"value": "bob@test.com"}]},
            ],
        }
        mock_people.people().connections().list().execute.side_effect = [page1, page2]
        with patch("src.gmail_client.build", return_value=mock_people):
            result = client.get_contacts(max_results=2000)
        assert len(result) == 2
```

Add this import at the top of the test file:

```python
from unittest.mock import MagicMock, patch
```

(Update the existing `from unittest.mock import MagicMock` import to include `patch`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_gmail_client.py::TestGetContacts -v`
Expected: FAIL

- [ ] **Step 3: Implement get_contacts**

Add to `src/gmail_client.py`. First, the `build` import is already present at line 9. The method:

```python
    def get_contacts(self, max_results: int = 2000) -> list[dict[str, Any]]:
        """Fetch Google contacts with email addresses via People API.

        Args:
            max_results: Maximum contacts to return.

        Returns:
            List of dicts with name and emails keys.
        """
        creds = self._token_mgr.get_credentials()
        people_svc = build("people", "v1", credentials=creds)
        contacts: list[dict[str, Any]] = []
        next_page: str | None = None

        while len(contacts) < max_results:
            page_size = min(1000, max_results - len(contacts))
            kwargs: dict[str, Any] = {
                "resourceName": "people/me",
                "pageSize": page_size,
                "personFields": "names,emailAddresses",
            }
            if next_page:
                kwargs["pageToken"] = next_page
            result = people_svc.people().connections().list(**kwargs).execute()
            for person in result.get("connections", []):
                emails = person.get("emailAddresses", [])
                if not emails:
                    continue
                names = person.get("names", [])
                name = names[0].get("displayName", "Unknown") if names else "Unknown"
                contacts.append({
                    "name": name,
                    "emails": [e["value"] for e in emails],
                })
            next_page = result.get("nextPageToken")
            if not next_page:
                break
        logger.info(f"Fetched {len(contacts)} contacts with email addresses")
        return contacts
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_gmail_client.py::TestGetContacts -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/gmail_client.py tests/unit/test_gmail_client.py
git commit -m "feat: add get_contacts via People API to GmailClient"
```

---

### Task 5: GmailClient — extract_unsubscribe_link

**Files:**
- Modify: `src/gmail_client.py`
- Test: `tests/unit/test_gmail_client.py`

- [ ] **Step 1: Write failing test**

```python
class TestExtractUnsubscribeLink:
    def test_extracts_https_link(self) -> None:
        mock_svc = MagicMock()
        mock_svc.users().messages().get().execute.return_value = {
            "id": "msg_001",
            "payload": {
                "headers": [
                    {"name": "List-Unsubscribe", "value": "<https://example.com/unsub?id=123>"},
                ],
            },
        }
        client = _make_client(mock_svc)
        result = client.extract_unsubscribe_link("msg_001")
        assert result["found"] is True
        assert result["unsubscribe_url"] == "https://example.com/unsub?id=123"
        assert result["unsubscribe_mailto"] is None

    def test_extracts_mailto_link(self) -> None:
        mock_svc = MagicMock()
        mock_svc.users().messages().get().execute.return_value = {
            "id": "msg_001",
            "payload": {
                "headers": [
                    {"name": "List-Unsubscribe", "value": "<mailto:unsub@example.com?subject=unsub>"},
                ],
            },
        }
        client = _make_client(mock_svc)
        result = client.extract_unsubscribe_link("msg_001")
        assert result["found"] is True
        assert result["unsubscribe_mailto"] == "mailto:unsub@example.com?subject=unsub"
        assert result["unsubscribe_url"] is None

    def test_extracts_both(self) -> None:
        mock_svc = MagicMock()
        mock_svc.users().messages().get().execute.return_value = {
            "id": "msg_001",
            "payload": {
                "headers": [
                    {"name": "List-Unsubscribe", "value": "<mailto:unsub@example.com>, <https://example.com/unsub>"},
                ],
            },
        }
        client = _make_client(mock_svc)
        result = client.extract_unsubscribe_link("msg_001")
        assert result["found"] is True
        assert result["unsubscribe_url"] == "https://example.com/unsub"
        assert result["unsubscribe_mailto"] == "mailto:unsub@example.com"

    def test_no_header_returns_not_found(self) -> None:
        mock_svc = MagicMock()
        mock_svc.users().messages().get().execute.return_value = {
            "id": "msg_001",
            "payload": {"headers": [{"name": "Subject", "value": "Hello"}]},
        }
        client = _make_client(mock_svc)
        result = client.extract_unsubscribe_link("msg_001")
        assert result["found"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_gmail_client.py::TestExtractUnsubscribeLink -v`
Expected: FAIL

- [ ] **Step 3: Implement extract_unsubscribe_link**

```python
    def extract_unsubscribe_link(self, message_id: str) -> dict[str, Any]:
        """Extract List-Unsubscribe header from a message.

        Args:
            message_id: The message ID to inspect.

        Returns:
            Dict with found, unsubscribe_url, unsubscribe_mailto.
        """
        svc = self._get_service()
        msg = svc.users().messages().get(
            userId="me", id=message_id, format="metadata",
            metadataHeaders=["List-Unsubscribe"],
        ).execute()
        headers = msg.get("payload", {}).get("headers", [])
        unsub_header = ""
        for h in headers:
            if h["name"].lower() == "list-unsubscribe":
                unsub_header = h["value"]
                break
        if not unsub_header:
            return {"found": False, "unsubscribe_url": None, "unsubscribe_mailto": None}

        import re
        links = re.findall(r"<([^>]+)>", unsub_header)
        url: str | None = None
        mailto: str | None = None
        for link in links:
            if link.startswith("https://") or link.startswith("http://"):
                url = link
            elif link.startswith("mailto:"):
                mailto = link
        return {"found": True, "unsubscribe_url": url, "unsubscribe_mailto": mailto}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_gmail_client.py::TestExtractUnsubscribeLink -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/gmail_client.py tests/unit/test_gmail_client.py
git commit -m "feat: add extract_unsubscribe_link to GmailClient"
```

---

### Task 6: Tool Handlers — src/tools/hygiene.py

**Files:**
- Create: `src/tools/hygiene.py`
- Test: `tests/unit/tools/test_hygiene.py`

- [ ] **Step 1: Write failing tests for all 6 handlers**

Create `tests/unit/tools/test_hygiene.py`:

```python
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.tools.hygiene import (
    handle_block_sender,
    handle_get_unsubscribe_link,
    handle_import_contacts_as_priority,
    handle_list_contacts,
    handle_report_spam,
    handle_trash_messages,
)


def _gmail_client() -> MagicMock:
    client = MagicMock()
    client.provider = "gmail"
    return client


def _outlook_client() -> MagicMock:
    client = MagicMock()
    client.provider = "outlook"
    return client


class TestHandleTrashMessages:
    def test_trash_by_ids(self) -> None:
        client = _gmail_client()
        client.trash_messages.return_value = {"trashed_count": 2, "message_ids": ["a", "b"]}
        result = handle_trash_messages({"messageIds": ["a", "b"]}, client)
        assert "Trashed 2 messages" in result["content"][0]["text"]

    def test_trash_by_query(self) -> None:
        client = _gmail_client()
        client.trash_by_query.return_value = {"trashed_count": 5, "message_ids": ["a"] * 5}
        result = handle_trash_messages({"query": "from:spam"}, client)
        assert "Trashed 5 messages" in result["content"][0]["text"]

    def test_rejects_outlook(self) -> None:
        client = _outlook_client()
        result = handle_trash_messages({"messageIds": ["a"]}, client)
        assert "only available for Gmail" in result["content"][0]["text"]

    def test_requires_ids_or_query(self) -> None:
        client = _gmail_client()
        result = handle_trash_messages({}, client)
        assert "messageIds or query" in result["content"][0]["text"]


class TestHandleBlockSender:
    def test_blocks_sender(self) -> None:
        client = _gmail_client()
        client.create_block_filter.return_value = {"filter_id": "f1", "existing_trashed": 3}
        result = handle_block_sender({"sender": "spam@test.com"}, client)
        text = result["content"][0]["text"]
        assert "spam@test.com" in text
        assert "3" in text

    def test_rejects_outlook(self) -> None:
        client = _outlook_client()
        result = handle_block_sender({"sender": "x"}, client)
        assert "only available for Gmail" in result["content"][0]["text"]


class TestHandleReportSpam:
    def test_reports_spam(self) -> None:
        client = _gmail_client()
        client.report_spam.return_value = {"reported_count": 4}
        result = handle_report_spam({"messageIds": ["a", "b", "c", "d"]}, client)
        assert "4" in result["content"][0]["text"]


class TestHandleListContacts:
    def test_lists_contacts(self) -> None:
        client = _gmail_client()
        client.get_contacts.return_value = [
            {"name": "Alice", "emails": ["alice@test.com"]},
        ]
        result = handle_list_contacts({}, client)
        assert "Alice" in result["content"][0]["text"]


class TestHandleGetUnsubscribeLink:
    def test_returns_link(self) -> None:
        client = _gmail_client()
        client.extract_unsubscribe_link.return_value = {
            "found": True,
            "unsubscribe_url": "https://example.com/unsub",
            "unsubscribe_mailto": None,
        }
        result = handle_get_unsubscribe_link({"messageId": "msg_001"}, client)
        assert "https://example.com/unsub" in result["content"][0]["text"]

    def test_not_found(self) -> None:
        client = _gmail_client()
        client.extract_unsubscribe_link.return_value = {
            "found": False, "unsubscribe_url": None, "unsubscribe_mailto": None,
        }
        result = handle_get_unsubscribe_link({"messageId": "msg_001"}, client)
        assert "No unsubscribe" in result["content"][0]["text"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/tools/test_hygiene.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Create src/tools/hygiene.py with all 6 handlers**

```python
"""Email hygiene tool handlers: trash, block, spam, contacts, unsubscribe."""

from __future__ import annotations

import json
from typing import Any

from loguru import logger

from ..email_client import EmailClient
from ..triage.cache import TriageCache
from ..triage.models import SenderTier
from ..triage.priority_senders import PrioritySenderManager


def _text_content(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


def _gmail_only(client: EmailClient) -> dict[str, Any] | None:
    if client.provider != "gmail":
        return _text_content("This tool is only available for Gmail accounts.")
    return None


def handle_trash_messages(args: dict[str, Any], client: EmailClient) -> dict[str, Any]:
    """Trash messages by IDs or search query."""
    guard = _gmail_only(client)
    if guard:
        return guard

    message_ids = args.get("messageIds")
    query = args.get("query")

    if not message_ids and not query:
        return _text_content("Provide messageIds or query to identify messages to trash.")

    if message_ids:
        result = client.trash_messages(message_ids)  # type: ignore[attr-defined]
    else:
        max_results = args.get("maxResults", 500)
        result = client.trash_by_query(query, max_results)  # type: ignore[attr-defined]

    return _text_content(
        f"Trashed {result['trashed_count']} messages.\n"
        f"Message IDs: {json.dumps(result['message_ids'][:20])}"
        + (f"\n... and {result['trashed_count'] - 20} more" if result["trashed_count"] > 20 else "")
    )


def handle_block_sender(args: dict[str, Any], client: EmailClient) -> dict[str, Any]:
    """Block a sender: create auto-delete filter + trash existing."""
    guard = _gmail_only(client)
    if guard:
        return guard

    sender = args.get("sender")
    if not sender:
        return _text_content("sender is required.")

    result = client.create_block_filter(sender)  # type: ignore[attr-defined]
    return _text_content(
        f"Blocked {sender}.\n"
        f"Filter ID: {result['filter_id']}\n"
        f"Existing messages trashed: {result['existing_trashed']}"
    )


def handle_report_spam(args: dict[str, Any], client: EmailClient) -> dict[str, Any]:
    """Report messages as spam."""
    guard = _gmail_only(client)
    if guard:
        return guard

    message_ids = args.get("messageIds")
    if not message_ids:
        return _text_content("messageIds is required.")

    result = client.report_spam(message_ids)  # type: ignore[attr-defined]
    return _text_content(f"Reported {result['reported_count']} messages as spam.")


def handle_list_contacts(args: dict[str, Any], client: EmailClient) -> dict[str, Any]:
    """List Google contacts with email addresses."""
    guard = _gmail_only(client)
    if guard:
        return guard

    max_results = args.get("maxResults", 2000)
    contacts = client.get_contacts(max_results)  # type: ignore[attr-defined]
    if not contacts:
        return _text_content("No contacts with email addresses found.")

    lines = [f"Found {len(contacts)} contacts with email addresses:\n"]
    for c in contacts:
        emails = ", ".join(c["emails"])
        lines.append(f"  {c['name']} <{emails}>")
    return _text_content("\n".join(lines))


def handle_import_contacts_as_priority(
    args: dict[str, Any], client: EmailClient, cache: TriageCache
) -> dict[str, Any]:
    """Import Google contacts as priority senders."""
    guard = _gmail_only(client)
    if guard:
        return guard

    tier_str = args.get("tier", "normal")
    try:
        tier = SenderTier(tier_str)
    except ValueError:
        return _text_content(f"Invalid tier: {tier_str}. Use critical, high, or normal.")

    contacts = client.get_contacts()  # type: ignore[attr-defined]
    if not contacts:
        return _text_content("No contacts with email addresses found.")

    mgr = PrioritySenderManager(cache)
    added = 0
    skipped = 0
    for contact in contacts:
        for email in contact["emails"]:
            if mgr.match(email):
                skipped += 1
            else:
                label = contact["name"]
                mgr.add(email, tier, label)
                added += 1

    return _text_content(
        f"Imported contacts as priority senders (tier={tier_str}).\n"
        f"Added: {added}\n"
        f"Skipped (already matched): {skipped}\n"
        f"Total contacts processed: {len(contacts)}"
    )


def handle_get_unsubscribe_link(
    args: dict[str, Any], client: EmailClient
) -> dict[str, Any]:
    """Extract unsubscribe link from a message."""
    guard = _gmail_only(client)
    if guard:
        return guard

    message_id = args.get("messageId")
    if not message_id:
        return _text_content("messageId is required.")

    result = client.extract_unsubscribe_link(message_id)  # type: ignore[attr-defined]
    if not result["found"]:
        return _text_content("No unsubscribe link found in this message.")

    lines = ["Unsubscribe options found:"]
    if result["unsubscribe_url"]:
        lines.append(f"  URL: {result['unsubscribe_url']}")
    if result["unsubscribe_mailto"]:
        lines.append(f"  Email: {result['unsubscribe_mailto']}")
    return _text_content("\n".join(lines))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/tools/test_hygiene.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/tools/hygiene.py tests/unit/tools/test_hygiene.py
git commit -m "feat: add hygiene tool handlers (trash, block, spam, contacts, unsub)"
```

---

### Task 7: Tool Registration — src/tools/__init__.py

**Files:**
- Modify: `src/tools/__init__.py`
- Test: `tests/unit/test_tool_registry.py`

- [ ] **Step 1: Write failing test**

Add to `tests/unit/test_tool_registry.py`:

```python
class TestHygieneToolsRegistered:
    def test_hygiene_tools_in_definitions(self) -> None:
        from src.tools import TOOL_DEFINITIONS
        tool_names = {t["name"] for t in TOOL_DEFINITIONS}
        hygiene_tools = {
            "gmail_trash_messages",
            "gmail_block_sender",
            "gmail_report_spam",
            "gmail_list_contacts",
            "gmail_import_contacts_as_priority",
            "gmail_get_unsubscribe_link",
        }
        assert hygiene_tools.issubset(tool_names)

    def test_total_tool_count(self) -> None:
        from src.tools import TOOL_DEFINITIONS
        assert len(TOOL_DEFINITIONS) == 28
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_tool_registry.py::TestHygieneToolsRegistered -v`
Expected: FAIL

- [ ] **Step 3: Add tool definitions and handler map entries**

In `src/tools/__init__.py`, add the import at the top with other imports:

```python
from .hygiene import (
    handle_block_sender,
    handle_get_unsubscribe_link,
    handle_import_contacts_as_priority,
    handle_list_contacts,
    handle_report_spam,
    handle_trash_messages,
)
```

Add these 6 entries to the `TOOL_DEFINITIONS` list (before the closing `]`):

```python
    {
        "name": "gmail_trash_messages",
        "description": "Trash messages by IDs or search query.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "messageIds": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of message IDs to trash",
                },
                "query": {
                    "type": "string",
                    "description": "Gmail search query to find messages to trash",
                },
                "maxResults": {
                    "type": "integer",
                    "default": 500,
                    "description": "Max messages to trash when using query",
                },
            },
            "required": [],
        },
    },
    {
        "name": "gmail_block_sender",
        "description": "Block a sender: create auto-delete filter and trash existing messages.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sender": {
                    "type": "string",
                    "description": "Email address or domain to block",
                },
            },
            "required": ["sender"],
        },
    },
    {
        "name": "gmail_report_spam",
        "description": "Report messages as spam (trains Gmail spam filter).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "messageIds": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Message IDs to report as spam",
                },
            },
            "required": ["messageIds"],
        },
    },
    {
        "name": "gmail_list_contacts",
        "description": "List Google contacts with email addresses.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "maxResults": {
                    "type": "integer",
                    "default": 2000,
                    "description": "Max contacts to return",
                },
            },
            "required": [],
        },
    },
    {
        "name": "gmail_import_contacts_as_priority",
        "description": "Import Google contacts as priority senders at a specified tier.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tier": {
                    "type": "string",
                    "enum": ["critical", "high", "normal"],
                    "default": "normal",
                    "description": "Priority tier for imported contacts",
                },
            },
            "required": [],
        },
    },
    {
        "name": "gmail_get_unsubscribe_link",
        "description": "Extract unsubscribe link from a message's List-Unsubscribe header.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "messageId": {
                    "type": "string",
                    "description": "Message ID to extract unsubscribe link from",
                },
            },
            "required": ["messageId"],
        },
    },
```

Add to `_HANDLER_MAP` (the regular handler map, not triage):

```python
    "gmail_trash_messages": handle_trash_messages,
    "gmail_block_sender": handle_block_sender,
    "gmail_report_spam": handle_report_spam,
    "gmail_list_contacts": handle_list_contacts,
    "gmail_get_unsubscribe_link": handle_get_unsubscribe_link,
```

Add `handle_import_contacts_as_priority` to `_TRIAGE_HANDLER_MAP` since it needs the `TriageCache`:

```python
    "gmail_import_contacts_as_priority": handle_import_contacts_as_priority,
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_tool_registry.py::TestHygieneToolsRegistered -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -v --tb=short`
Expected: All existing + new tests PASS

- [ ] **Step 6: Run linting and type checks**

Run: `ruff check src/tools/hygiene.py src/gmail_client.py src/tools/__init__.py && ruff format --check src/ tests/`
Run: `mypy src/tools/hygiene.py src/gmail_client.py --strict`

- [ ] **Step 7: Commit**

```bash
git add src/tools/__init__.py src/tools/hygiene.py tests/unit/test_tool_registry.py
git commit -m "feat: register 6 hygiene tools in MCP tool registry (28 total)"
```

---

### Task 8: Integration Smoke Test

**Files:**
- Test: `tests/integration/test_hygiene_roundtrip.py`

- [ ] **Step 1: Write integration test**

Create `tests/integration/test_hygiene_roundtrip.py`:

```python
"""Integration tests for hygiene tools via ToolRegistry."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.tools import ToolRegistry
from src.models import ToolCallParams


@pytest.fixture
def mock_gmail_registry() -> ToolRegistry:
    mock_client = MagicMock()
    mock_client.provider = "gmail"
    mock_client.email_address = "test@gmail.com"

    mock_account_registry = MagicMock()
    mock_account_registry.get.return_value = mock_client
    return ToolRegistry(
        account_registry=mock_account_registry,
        cache_db_path=":memory:",
    )


class TestTrashMessagesRoundtrip:
    def test_trash_by_query_via_registry(self, mock_gmail_registry: ToolRegistry) -> None:
        client = mock_gmail_registry._registry.get()
        client.trash_by_query.return_value = {"trashed_count": 3, "message_ids": ["a", "b", "c"]}
        params = ToolCallParams(name="gmail_trash_messages", arguments={"query": "from:test"})
        result = mock_gmail_registry.execute_tool(params)
        assert "3" in result["content"][0]["text"]


class TestBlockSenderRoundtrip:
    def test_block_via_registry(self, mock_gmail_registry: ToolRegistry) -> None:
        client = mock_gmail_registry._registry.get()
        client.create_block_filter.return_value = {"filter_id": "f1", "existing_trashed": 5}
        params = ToolCallParams(name="gmail_block_sender", arguments={"sender": "spam@test.com"})
        result = mock_gmail_registry.execute_tool(params)
        assert "spam@test.com" in result["content"][0]["text"]


class TestImportContactsRoundtrip:
    def test_import_via_registry(self, mock_gmail_registry: ToolRegistry) -> None:
        client = mock_gmail_registry._registry.get()
        client.get_contacts.return_value = [
            {"name": "Test User", "emails": ["testuser@example.com"]},
        ]
        params = ToolCallParams(
            name="gmail_import_contacts_as_priority",
            arguments={"tier": "normal"},
        )
        result = mock_gmail_registry.execute_tool(params)
        assert "Added: 1" in result["content"][0]["text"]
```

- [ ] **Step 2: Run integration tests**

Run: `pytest tests/integration/test_hygiene_roundtrip.py -v`
Expected: All PASS

- [ ] **Step 3: Run full verification pipeline**

Run: `ruff format --check src/ tests/ && ruff check src/ tests/ && mypy src/ --strict && pytest tests/ -v --tb=short`

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_hygiene_roundtrip.py
git commit -m "test: add hygiene tools integration roundtrip tests"
```

---

### Task 9: Execute Immediate Actions

After all tools are built and tested:

- [ ] **Step 1: Import contacts as priority senders**

Use MCP tool: `gmail_import_contacts_as_priority` with `tier=normal`

- [ ] **Step 2: Trash Earth Breeze emails**

Use MCP tool: `gmail_trash_messages` with `query="from:earthbreeze"`

- [ ] **Step 3: Trash Game 7 Staffing emails**

Use MCP tool: `gmail_trash_messages` with `query="from:game7staffing"`

- [ ] **Step 4: Verify priority senders list**

Use MCP tool: `gmail_list_priority_senders` to confirm contacts were added
