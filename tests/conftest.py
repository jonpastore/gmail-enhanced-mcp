from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_gmail_service() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_gmail_client(mock_gmail_service: MagicMock) -> MagicMock:
    client = MagicMock()
    client.service = mock_gmail_service
    return client


@pytest.fixture
def sample_message() -> dict[str, Any]:
    return {
        "id": "msg_001",
        "threadId": "thread_001",
        "labelIds": ["INBOX", "UNREAD"],
        "snippet": "Hello, this is a test email",
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "From", "value": "sender@example.com"},
                {"name": "To", "value": "jpastore79@gmail.com"},
                {"name": "Subject", "value": "Test Email"},
                {"name": "Date", "value": "Mon, 10 Mar 2026 10:00:00 -0500"},
            ],
            "body": {"data": "SGVsbG8sIHRoaXMgaXMgYSB0ZXN0IGVtYWls", "size": 27},
            "parts": [],
        },
        "sizeEstimate": 1024,
        "internalDate": "1741608000000",
    }


@pytest.fixture
def sample_thread(sample_message: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "thread_001",
        "messages": [sample_message],
    }


@pytest.fixture
def sample_profile() -> dict[str, Any]:
    return {
        "emailAddress": "jpastore79@gmail.com",
        "messagesTotal": 50000,
        "threadsTotal": 25000,
        "historyId": "12345",
    }


@pytest.fixture
def tmp_template_dir(tmp_path: Path) -> Path:
    tpl_dir = tmp_path / "templates"
    tpl_dir.mkdir()
    return tpl_dir


@pytest.fixture
def sample_attachment_bytes() -> bytes:
    return b"%PDF-1.4 fake pdf content for testing"
