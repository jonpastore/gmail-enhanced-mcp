"""Unit tests for ai_context tool handlers."""

from __future__ import annotations

import base64
import json
from typing import Any
from unittest.mock import MagicMock, patch

from src.handler_context import HandlerContext


def _ctx(client=None) -> HandlerContext:
    return HandlerContext(client=client or MagicMock())


def _make_payload(
    from_addr: str = "alice@example.com",
    to_addr: str = "me@gmail.com",
    subject: str = "Hello",
    date_str: str = "Mon, 01 Apr 2026 10:00:00 -0400",
    body_text: str = "Hi there",
    attachments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    parts: list[dict[str, Any]] = []
    if attachments:
        for att in attachments:
            parts.append(
                {
                    "filename": att["filename"],
                    "body": {"attachmentId": att.get("attachment_id", "att1")},
                }
            )

    encoded = base64.urlsafe_b64encode(body_text.encode()).decode()
    return {
        "headers": [
            {"name": "From", "value": from_addr},
            {"name": "To", "value": to_addr},
            {"name": "CC", "value": ""},
            {"name": "Subject", "value": subject},
            {"name": "Date", "value": date_str},
        ],
        "mimeType": "text/plain",
        "body": {"data": encoded},
        "parts": parts,
    }


def _make_message(
    msg_id: str = "m1",
    thread_id: str = "t1",
    from_addr: str = "alice@example.com",
    to_addr: str = "me@gmail.com",
    subject: str = "Hello",
    body_text: str = "Hi there",
    date_str: str = "Mon, 01 Apr 2026 10:00:00 -0400",
    attachments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "id": msg_id,
        "threadId": thread_id,
        "payload": _make_payload(
            from_addr=from_addr,
            to_addr=to_addr,
            subject=subject,
            date_str=date_str,
            body_text=body_text,
            attachments=attachments,
        ),
    }


class TestHandleSummarizeThread:
    def _make_client(
        self,
        thread_messages: list[dict[str, Any]],
        email_address: str = "me@gmail.com",
    ) -> MagicMock:
        client = MagicMock()
        client.email_address = email_address
        client.read_thread.return_value = {"messages": thread_messages}
        return client

    def test_requires_thread_id(self) -> None:
        from src.tools.ai_context import handle_summarize_thread

        client = self._make_client([])
        result = handle_summarize_thread({}, _ctx(client))
        assert result["isError"] is True
        assert "threadId" in result["content"][0]["text"]

    def test_basic_thread_summary_two_messages(self) -> None:
        from src.tools.ai_context import handle_summarize_thread

        msgs = [
            _make_message(msg_id="m1", from_addr="alice@example.com", body_text="Hello"),
            _make_message(
                msg_id="m2",
                from_addr="bob@example.com",
                to_addr="alice@example.com",
                body_text="Hi Alice",
            ),
        ]
        client = self._make_client(msgs)
        result = handle_summarize_thread({"threadId": "t1"}, _ctx(client))
        assert not result.get("isError")
        data = json.loads(result["content"][0]["text"])
        assert data["message_count"] == 2
        assert data["thread_id"] == "t1"
        participant_emails = {p["email"] for p in data["participants"]}
        assert "alice@example.com" in participant_emails
        assert "bob@example.com" in participant_emails
        assert len(data["timeline"]) == 2

    def test_key_asks_extraction(self) -> None:
        from src.tools.ai_context import handle_summarize_thread

        msgs = [
            _make_message(
                msg_id="m1",
                from_addr="boss@work.com",
                to_addr="me@gmail.com",
                body_text="Could you please send me the report by Friday?",
            ),
        ]
        client = self._make_client(msgs)
        result = handle_summarize_thread({"threadId": "t1"}, _ctx(client))
        data = json.loads(result["content"][0]["text"])
        assert len(data["key_asks"]) >= 1
        asks_lower = [a.lower() for a in data["key_asks"]]
        assert any("please" in a or "could you" in a for a in asks_lower)

    def test_open_questions_extraction(self) -> None:
        from src.tools.ai_context import handle_summarize_thread

        msgs = [
            _make_message(
                msg_id="m1",
                from_addr="colleague@work.com",
                to_addr="me@gmail.com",
                body_text="What time works for you? Can we meet tomorrow?",
            ),
        ]
        client = self._make_client(msgs)
        result = handle_summarize_thread({"threadId": "t1"}, _ctx(client))
        data = json.loads(result["content"][0]["text"])
        assert len(data["open_questions"]) >= 1
        assert any("?" in q for q in data["open_questions"])

    def test_attachments_collected(self) -> None:
        from src.tools.ai_context import handle_summarize_thread

        msgs = [
            _make_message(
                msg_id="m1",
                from_addr="sender@example.com",
                body_text="See attached file",
                attachments=[{"filename": "report.pdf", "attachment_id": "att001"}],
            ),
        ]
        client = self._make_client(msgs)
        result = handle_summarize_thread({"threadId": "t1"}, _ctx(client))
        data = json.loads(result["content"][0]["text"])
        assert len(data["attachments"]) == 1
        assert data["attachments"][0]["filename"] == "report.pdf"

    def test_empty_thread_returns_error(self) -> None:
        from src.tools.ai_context import handle_summarize_thread

        client = MagicMock()
        client.email_address = "me@gmail.com"
        client.read_thread.side_effect = RuntimeError("Thread not found")
        result = handle_summarize_thread({"threadId": "t_missing"}, _ctx(client))
        assert result["isError"] is True

    def test_single_message_thread(self) -> None:
        from src.tools.ai_context import handle_summarize_thread

        msgs = [
            _make_message(
                msg_id="m1",
                from_addr="sender@example.com",
                body_text="Just one message",
            ),
        ]
        client = self._make_client(msgs)
        result = handle_summarize_thread({"threadId": "t1"}, _ctx(client))
        assert not result.get("isError")
        data = json.loads(result["content"][0]["text"])
        assert data["message_count"] == 1

    def test_questions_from_me_not_included(self) -> None:
        from src.tools.ai_context import handle_summarize_thread

        msgs = [
            _make_message(
                msg_id="m1",
                from_addr="me@gmail.com",
                body_text="Can you send the report? What is the deadline?",
            ),
        ]
        client = self._make_client(msgs, email_address="me@gmail.com")
        result = handle_summarize_thread({"threadId": "t1"}, _ctx(client))
        data = json.loads(result["content"][0]["text"])
        assert data["open_questions"] == []


class TestHandleNeedsReply:
    def _make_client(
        self,
        search_results: list[dict[str, Any]],
        messages: dict[str, dict[str, Any]] | None = None,
        threads: dict[str, dict[str, Any]] | None = None,
        email_address: str = "me@gmail.com",
    ) -> MagicMock:
        client = MagicMock()
        client.email_address = email_address

        client.search_messages.return_value = {"messages": search_results}

        msg_store = messages or {}
        thread_store = threads or {}

        def read_msg(msg_id: str) -> dict[str, Any]:
            return msg_store.get(msg_id, _make_message(msg_id=msg_id))

        def read_thread(thread_id: str) -> dict[str, Any]:
            if thread_id in thread_store:
                return thread_store[thread_id]
            msg = msg_store.get(thread_id, _make_message(msg_id=thread_id, thread_id=thread_id))
            return {"messages": [msg]}

        client.read_message.side_effect = read_msg
        client.read_thread.side_effect = read_thread
        return client

    def test_finds_message_needing_reply(self) -> None:
        from src.tools.ai_context import handle_needs_reply

        msg = _make_message(
            msg_id="m1",
            thread_id="t1",
            from_addr="colleague@work.com",
            to_addr="me@gmail.com",
            subject="Quick question",
            body_text="Could you review this? What do you think?",
        )
        client = self._make_client(
            search_results=[{"id": "m1", "threadId": "t1"}],
            messages={"m1": msg},
            threads={"t1": {"messages": [msg]}},
        )
        result = handle_needs_reply({}, _ctx(client))
        assert not result.get("isError")
        data = json.loads(result["content"][0]["text"])
        assert data["count"] >= 1

    def test_no_results_returns_message(self) -> None:
        from src.tools.ai_context import handle_needs_reply

        client = MagicMock()
        client.email_address = "me@gmail.com"
        client.search_messages.return_value = {"messages": []}
        result = handle_needs_reply({}, _ctx(client))
        assert not result.get("isError")
        assert "No unread inbox" in result["content"][0]["text"]

    def test_days_back_parameter_affects_query(self) -> None:
        from src.tools.ai_context import handle_needs_reply

        client = MagicMock()
        client.email_address = "me@gmail.com"
        client.search_messages.return_value = {"messages": []}
        handle_needs_reply({"daysBack": 14}, _ctx(client))
        call_args = client.search_messages.call_args
        assert "after:" in call_args.kwargs.get("q", call_args.args[0] if call_args.args else "")

    def test_skips_junk_senders(self) -> None:
        from src.tools.ai_context import handle_needs_reply

        msg = _make_message(
            msg_id="m1",
            thread_id="t1",
            from_addr="newsletter@massmail.com",
            to_addr="me@gmail.com",
            subject="Weekly Digest",
            body_text="Check out our weekly newsletter",
        )
        my_sent = _make_message(
            msg_id="m2",
            thread_id="t1",
            from_addr="me@gmail.com",
            to_addr="newsletter@massmail.com",
            body_text="Please unsubscribe me",
        )
        client = self._make_client(
            search_results=[{"id": "m1", "threadId": "t1"}],
            messages={"m1": msg},
            threads={"t1": {"messages": [msg, my_sent]}},
        )
        with patch("src.tools.ai_context.JunkDetector") as MockJunk:
            junk_instance = MagicMock()
            junk_result = MagicMock()
            junk_result.is_junk = True
            junk_instance.analyze.return_value = junk_result
            MockJunk.return_value = junk_instance

            result = handle_needs_reply({}, _ctx(client))
            data = json.loads(result["content"][0]["text"])
            assert data["count"] == 0

    def test_skips_when_last_reply_is_mine(self) -> None:
        from src.tools.ai_context import handle_needs_reply

        first_msg = _make_message(
            msg_id="m1",
            thread_id="t1",
            from_addr="colleague@work.com",
            to_addr="team@work.com",
            body_text="FYI sharing this update with the team.",
        )
        my_reply = _make_message(
            msg_id="m2",
            thread_id="t1",
            from_addr="me@gmail.com",
            to_addr="team@work.com",
            body_text="Thanks for sharing.",
        )
        client = self._make_client(
            search_results=[{"id": "m1", "threadId": "t1"}],
            messages={"m1": first_msg},
            threads={"t1": {"messages": [first_msg, my_reply]}},
        )
        result = handle_needs_reply({}, _ctx(client))
        data = json.loads(result["content"][0]["text"])
        assert data["count"] == 0

    def test_search_failure_returns_error(self) -> None:
        from src.tools.ai_context import handle_needs_reply

        client = MagicMock()
        client.email_address = "me@gmail.com"
        client.search_messages.side_effect = RuntimeError("API error")
        result = handle_needs_reply({}, _ctx(client))
        assert result["isError"] is True
