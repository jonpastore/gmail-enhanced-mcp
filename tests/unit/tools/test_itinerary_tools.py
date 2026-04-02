"""Unit tests for handle_extract_itinerary."""

from __future__ import annotations

import base64
import json
from datetime import date, timedelta
from typing import Any
from unittest.mock import MagicMock, patch


def _make_message(
    msg_id: str = "m1",
    from_addr: str = "confirm@delta.com",
    subject: str = "Flight Confirmation",
    body_text: str = "PNR: ABC123 Flight DL 200 JFK to LAX on 2026-05-01",
) -> dict[str, Any]:
    return {
        "id": msg_id,
        "threadId": "t1",
        "payload": {
            "headers": [
                {"name": "From", "value": from_addr},
                {"name": "Subject", "value": subject},
            ],
            "mimeType": "text/plain",
            "body": {"data": base64.urlsafe_b64encode(body_text.encode()).decode()},
        },
    }


def _make_client(
    messages: list[dict[str, Any]] | None = None,
    stubs: list[dict[str, Any]] | None = None,
) -> MagicMock:
    client = MagicMock()
    msg_list = messages or []
    stub_list = stubs or [{"id": m["id"]} for m in msg_list]

    client.search_messages.return_value = {"messages": stub_list}

    msg_map = {m["id"]: m for m in msg_list}

    def read_msg(msg_id: str) -> dict[str, Any]:
        return msg_map[msg_id]

    client.read_message.side_effect = read_msg
    return client


class TestHandleExtractItinerary:
    def test_basic_itinerary_extraction(self) -> None:
        from src.tools.itinerary import handle_extract_itinerary

        msg = _make_message("m1", "confirm@delta.com", "Flight Confirmation")
        client = _make_client([msg])

        today = date.today()
        args = {
            "dateFrom": today.isoformat(),
            "dateTo": (today + timedelta(days=10)).isoformat(),
        }

        with patch("src.tools.itinerary.ItineraryParser") as MockParser:
            mock_parser = MagicMock()
            mock_itinerary = MagicMock()
            mock_itinerary.model_dump.return_value = {
                "trips": [
                    {
                        "type": "flight",
                        "provider": "Delta",
                        "confirmation_number": "ABC123",
                        "start_date": "2026-05-01",
                        "end_date": None,
                        "details": "Flight DL200 | JFK -> LAX",
                        "source_message_id": "m1",
                    }
                ]
            }
            mock_parser.parse_messages.return_value = mock_itinerary
            MockParser.return_value = mock_parser

            result = handle_extract_itinerary(args, client)

        assert not result.get("isError")
        data = json.loads(result["content"][0]["text"])
        assert len(data["trips"]) == 1
        assert data["trips"][0]["type"] == "flight"

    def test_date_from_after_date_to_returns_error(self) -> None:
        from src.tools.itinerary import handle_extract_itinerary

        client = MagicMock()
        args = {"dateFrom": "2026-06-01", "dateTo": "2026-05-01"}
        result = handle_extract_itinerary(args, client)
        assert result["isError"] is True
        assert "before" in result["content"][0]["text"].lower()

    def test_date_from_equal_to_date_to_returns_error(self) -> None:
        from src.tools.itinerary import handle_extract_itinerary

        client = MagicMock()
        args = {"dateFrom": "2026-05-01", "dateTo": "2026-05-01"}
        result = handle_extract_itinerary(args, client)
        assert result["isError"] is True

    def test_invalid_date_format_returns_error(self) -> None:
        from src.tools.itinerary import handle_extract_itinerary

        client = MagicMock()
        args = {"dateFrom": "01/05/2026", "dateTo": "2026-06-01"}
        result = handle_extract_itinerary(args, client)
        assert result["isError"] is True
        assert "YYYY-MM-DD" in result["content"][0]["text"]

    def test_no_results_returns_empty_message(self) -> None:
        from src.tools.itinerary import handle_extract_itinerary

        client = MagicMock()
        client.search_messages.return_value = {"messages": []}

        today = date.today()
        args = {
            "dateFrom": today.isoformat(),
            "dateTo": (today + timedelta(days=10)).isoformat(),
        }
        result = handle_extract_itinerary(args, client)
        assert not result.get("isError")
        assert "No travel-related messages" in result["content"][0]["text"]

    def test_default_date_range_today_plus_30(self) -> None:
        from src.tools.itinerary import handle_extract_itinerary

        client = MagicMock()
        client.search_messages.return_value = {"messages": []}

        today = date.today()
        handle_extract_itinerary({}, client)

        call_kwargs = client.search_messages.call_args
        query = call_kwargs.kwargs.get("q", "")
        after_str = today.strftime("%Y/%m/%d")
        before_str = (today + timedelta(days=30)).strftime("%Y/%m/%d")
        assert after_str in query
        assert before_str in query

    def test_search_failure_returns_error(self) -> None:
        from src.tools.itinerary import handle_extract_itinerary

        client = MagicMock()
        client.search_messages.side_effect = RuntimeError("API error")

        today = date.today()
        args = {
            "dateFrom": today.isoformat(),
            "dateTo": (today + timedelta(days=10)).isoformat(),
        }
        result = handle_extract_itinerary(args, client)
        assert result["isError"] is True
        assert "Search failed" in result["content"][0]["text"]

    def test_parser_called_with_fetched_messages(self) -> None:
        from src.tools.itinerary import handle_extract_itinerary

        msg1 = _make_message("m1")
        msg2 = _make_message("m2", "noreply@marriott.com", "Hotel Booking")
        client = _make_client([msg1, msg2])

        today = date.today()
        args = {
            "dateFrom": today.isoformat(),
            "dateTo": (today + timedelta(days=30)).isoformat(),
        }

        with patch("src.tools.itinerary.ItineraryParser") as MockParser:
            mock_parser = MagicMock()
            mock_itinerary = MagicMock()
            mock_itinerary.model_dump.return_value = {"trips": []}
            mock_parser.parse_messages.return_value = mock_itinerary
            MockParser.return_value = mock_parser

            handle_extract_itinerary(args, client)

            called_messages = mock_parser.parse_messages.call_args[0][0]
            assert len(called_messages) == 2

    def test_unreadable_message_skipped_gracefully(self) -> None:
        from src.tools.itinerary import handle_extract_itinerary

        client = MagicMock()
        client.search_messages.return_value = {
            "messages": [{"id": "m_bad"}, {"id": "m_good"}]
        }

        good_msg = _make_message("m_good")

        def read_msg(msg_id: str) -> dict[str, Any]:
            if msg_id == "m_bad":
                raise RuntimeError("Not found")
            return good_msg

        client.read_message.side_effect = read_msg

        today = date.today()
        args = {
            "dateFrom": today.isoformat(),
            "dateTo": (today + timedelta(days=10)).isoformat(),
        }

        with patch("src.tools.itinerary.ItineraryParser") as MockParser:
            mock_parser = MagicMock()
            mock_itinerary = MagicMock()
            mock_itinerary.model_dump.return_value = {"trips": []}
            mock_parser.parse_messages.return_value = mock_itinerary
            MockParser.return_value = mock_parser

            result = handle_extract_itinerary(args, client)
            assert not result.get("isError")
            called_messages = mock_parser.parse_messages.call_args[0][0]
            assert len(called_messages) == 1
            assert called_messages[0]["id"] == "m_good"
