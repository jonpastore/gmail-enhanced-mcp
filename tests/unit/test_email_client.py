from __future__ import annotations

from src.email_client import EmailClient
from src.gmail_client import GmailClient


class TestEmailClientInterface:
    def test_gmail_client_is_email_client(self) -> None:
        assert issubclass(GmailClient, EmailClient)

    def test_email_client_has_required_methods(self) -> None:
        methods = [
            "get_profile",
            "search_messages",
            "read_message",
            "read_thread",
            "download_attachment",
            "list_labels",
            "modify_thread_labels",
            "list_drafts",
            "create_draft",
            "update_draft",
            "send_draft",
            "send_email",
            "build_mime_message",
        ]
        for method in methods:
            assert hasattr(EmailClient, method), f"Missing method: {method}"

    def test_email_client_has_properties(self) -> None:
        assert hasattr(EmailClient, "email_address")
        assert hasattr(EmailClient, "provider")
