"""Unit tests for handle_batch_reply."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

from src.handler_context import HandlerContext


def _ctx(client=None) -> HandlerContext:
    return HandlerContext(client=client or MagicMock())


def _make_original_message(
    msg_id: str = "m1",
    from_addr: str = "sender@example.com",
    subject: str = "Original Subject",
) -> dict[str, Any]:
    return {
        "id": msg_id,
        "threadId": "t1",
        "payload": {
            "headers": [
                {"name": "From", "value": from_addr},
                {"name": "Subject", "value": subject},
            ],
            "body": {"data": ""},
            "parts": [],
        },
    }


def _make_client(messages: dict[str, dict[str, Any]] | None = None) -> MagicMock:
    client = MagicMock()
    msg_store = messages or {}

    def read_msg(msg_id: str) -> dict[str, Any]:
        if msg_id in msg_store:
            return msg_store[msg_id]
        raise KeyError(f"Message {msg_id} not found")

    client.read_message.side_effect = read_msg
    client.create_draft.return_value = {"id": "draft_001"}
    return client


class TestHandleBatchReply:
    def test_creates_drafts_for_multiple_replies(self) -> None:
        from src.tools.batch_reply import handle_batch_reply

        messages = {
            "m1": _make_original_message("m1", "alice@example.com", "Project Update"),
            "m2": _make_original_message("m2", "bob@example.com", "Meeting Request"),
        }
        client = _make_client(messages)
        client.create_draft.side_effect = [{"id": "draft_001"}, {"id": "draft_002"}]

        args = {
            "replies": [
                {"messageId": "m1", "threadId": "t1", "body": "Thanks Alice!"},
                {"messageId": "m2", "threadId": "t2", "body": "Sounds good Bob!"},
            ]
        }
        result = handle_batch_reply(args, _ctx(client))
        assert not result.get("isError")
        data = json.loads(result["content"][0]["text"])
        assert data["drafts_created"] == 2
        assert len(data["draft_ids"]) == 2

    def test_returns_draft_ids(self) -> None:
        from src.tools.batch_reply import handle_batch_reply

        messages = {"m1": _make_original_message("m1")}
        client = _make_client(messages)
        client.create_draft.return_value = {"id": "draft_abc"}

        args = {"replies": [{"messageId": "m1", "threadId": "t1", "body": "Reply body"}]}
        result = handle_batch_reply(args, _ctx(client))
        data = json.loads(result["content"][0]["text"])
        assert "draft_abc" in data["draft_ids"]

    def test_max_20_limit_enforced(self) -> None:
        from src.tools.batch_reply import handle_batch_reply

        client = MagicMock()
        replies = [{"messageId": f"m{i}", "threadId": f"t{i}", "body": "reply"} for i in range(21)]
        result = handle_batch_reply({"replies": replies}, _ctx(client))
        assert result["isError"] is True
        assert "20" in result["content"][0]["text"]

    def test_exactly_20_replies_allowed(self) -> None:
        from src.tools.batch_reply import handle_batch_reply

        messages = {
            f"m{i}": _make_original_message(f"m{i}", f"sender{i}@example.com", f"Subject {i}")
            for i in range(20)
        }
        client = _make_client(messages)
        client.create_draft.return_value = {"id": "draft_x"}

        replies = [{"messageId": f"m{i}", "threadId": f"t{i}", "body": "reply"} for i in range(20)]
        result = handle_batch_reply({"replies": replies}, _ctx(client))
        assert not result.get("isError")
        data = json.loads(result["content"][0]["text"])
        assert data["drafts_created"] == 20

    def test_partial_failure_others_succeed(self) -> None:
        from src.tools.batch_reply import handle_batch_reply

        messages = {
            "m1": _make_original_message("m1", "alice@example.com", "Hello"),
        }
        client = _make_client(messages)
        client.create_draft.side_effect = [
            {"id": "draft_001"},
            RuntimeError("Gmail API down"),
        ]

        messages["m2"] = _make_original_message("m2", "bob@example.com", "Hey")
        client.read_message.side_effect = lambda mid: messages[mid]

        args = {
            "replies": [
                {"messageId": "m1", "threadId": "t1", "body": "Thanks"},
                {"messageId": "m2", "threadId": "t2", "body": "Sure"},
            ]
        }
        result = handle_batch_reply(args, _ctx(client))
        data = json.loads(result["content"][0]["text"])
        assert data["drafts_created"] == 1
        assert len(data["errors"]) == 1

    def test_empty_replies_list_returns_error(self) -> None:
        from src.tools.batch_reply import handle_batch_reply

        client = MagicMock()
        result = handle_batch_reply({"replies": []}, _ctx(client))
        assert result["isError"] is True
        assert "required" in result["content"][0]["text"].lower()

    def test_missing_replies_key_returns_error(self) -> None:
        from src.tools.batch_reply import handle_batch_reply

        client = MagicMock()
        result = handle_batch_reply({}, _ctx(client))
        assert result["isError"] is True

    def test_entry_missing_body_skipped_with_error(self) -> None:
        from src.tools.batch_reply import handle_batch_reply

        messages = {"m1": _make_original_message("m1")}
        client = _make_client(messages)

        args = {
            "replies": [
                {"messageId": "m1", "threadId": "t1"},
            ]
        }
        result = handle_batch_reply(args, _ctx(client))
        data = json.loads(result["content"][0]["text"])
        assert data["drafts_created"] == 0
        assert len(data["errors"]) == 1

    def test_subject_override_used_when_provided(self) -> None:
        from src.tools.batch_reply import handle_batch_reply

        messages = {"m1": _make_original_message("m1", "alice@example.com", "Original")}
        client = _make_client(messages)
        client.create_draft.return_value = {"id": "draft_001"}

        args = {
            "replies": [
                {
                    "messageId": "m1",
                    "threadId": "t1",
                    "body": "My reply",
                    "subject": "Custom Subject",
                }
            ]
        }
        handle_batch_reply(args, _ctx(client))
        call_kwargs = client.create_draft.call_args
        assert call_kwargs.kwargs.get("subject") == "Custom Subject"

    def test_re_prefix_added_to_subject(self) -> None:
        from src.tools.batch_reply import handle_batch_reply

        messages = {"m1": _make_original_message("m1", "alice@example.com", "Hello")}
        client = _make_client(messages)
        client.create_draft.return_value = {"id": "draft_001"}

        args = {"replies": [{"messageId": "m1", "threadId": "t1", "body": "Reply"}]}
        handle_batch_reply(args, _ctx(client))
        call_kwargs = client.create_draft.call_args
        assert call_kwargs.kwargs.get("subject") == "Re: Hello"

    def test_already_re_subject_not_double_prefixed(self) -> None:
        from src.tools.batch_reply import handle_batch_reply

        messages = {"m1": _make_original_message("m1", "alice@example.com", "Re: Hello")}
        client = _make_client(messages)
        client.create_draft.return_value = {"id": "draft_001"}

        args = {"replies": [{"messageId": "m1", "threadId": "t1", "body": "Reply"}]}
        handle_batch_reply(args, _ctx(client))
        call_kwargs = client.create_draft.call_args
        assert call_kwargs.kwargs.get("subject") == "Re: Hello"

    def test_message_read_failure_recorded_in_errors(self) -> None:
        from src.tools.batch_reply import handle_batch_reply

        client = MagicMock()
        client.read_message.side_effect = RuntimeError("Not found")

        args = {"replies": [{"messageId": "m_bad", "threadId": "t1", "body": "reply"}]}
        result = handle_batch_reply(args, _ctx(client))
        data = json.loads(result["content"][0]["text"])
        assert data["drafts_created"] == 0
        assert len(data["errors"]) == 1
        assert "m_bad" in data["errors"][0]
