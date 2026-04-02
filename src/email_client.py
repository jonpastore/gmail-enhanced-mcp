from __future__ import annotations

import mimetypes
from abc import ABC, abstractmethod
from email.mime.application import MIMEApplication
from email.mime.audio import MIMEAudio
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

import requests

BLOCKED_EXTENSIONS = {".exe", ".bat", ".cmd", ".scr", ".js", ".vbs", ".msi"}
MAX_ATTACHMENT_SIZE = 25 * 1024 * 1024


class EmailClient(ABC):
    @property
    @abstractmethod
    def email_address(self) -> str: ...

    @property
    @abstractmethod
    def provider(self) -> str: ...

    @abstractmethod
    def get_profile(self) -> dict[str, Any]: ...

    @abstractmethod
    def search_messages(
        self,
        q: str | None = None,
        max_results: int = 20,
        page_token: str | None = None,
        include_spam_trash: bool = False,
    ) -> dict[str, Any]: ...

    @abstractmethod
    def read_message(self, message_id: str) -> dict[str, Any]: ...

    @abstractmethod
    def read_thread(self, thread_id: str) -> dict[str, Any]: ...

    @abstractmethod
    def download_attachment(self, message_id: str, attachment_id: str, save_path: str) -> str: ...

    @abstractmethod
    def list_labels(self) -> list[dict[str, Any]]: ...

    @abstractmethod
    def modify_thread_labels(
        self,
        thread_id: str,
        add_label_ids: list[str] | None = None,
        remove_label_ids: list[str] | None = None,
    ) -> dict[str, Any]: ...

    @abstractmethod
    def list_drafts(
        self, max_results: int = 20, page_token: str | None = None
    ) -> dict[str, Any]: ...

    @abstractmethod
    def create_draft(
        self,
        to: str | None = None,
        subject: str | None = None,
        body: str = "",
        content_type: str = "text/plain",
        cc: str | None = None,
        bcc: str | None = None,
        thread_id: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]: ...

    @abstractmethod
    def update_draft(
        self,
        draft_id: str,
        to: str | None = None,
        subject: str | None = None,
        body: str = "",
        content_type: str = "text/plain",
        cc: str | None = None,
        bcc: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]: ...

    @abstractmethod
    def send_draft(self, draft_id: str) -> dict[str, Any]: ...

    @abstractmethod
    def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        content_type: str = "text/plain",
        cc: str | None = None,
        bcc: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]: ...

    def build_mime_message(
        self,
        to: str | None = None,
        subject: str | None = None,
        body: str = "",
        content_type: str = "text/plain",
        cc: str | None = None,
        bcc: str | None = None,
        thread_id: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> MIMEBase:
        msg: MIMEBase
        if attachments:
            multi = MIMEMultipart("mixed")
            text_part = MIMEText(body, "html" if content_type == "text/html" else "plain")
            multi.attach(text_part)
            for att in attachments:
                att_part = self._resolve_attachment(att)
                multi.attach(att_part)
            msg = multi
        else:
            subtype = "html" if content_type == "text/html" else "plain"
            msg = MIMEText(body, subtype)

        if to:
            msg["To"] = to
        if subject:
            msg["Subject"] = subject
        if cc:
            msg["Cc"] = cc
        if bcc:
            msg["Bcc"] = bcc
        return msg

    def _resolve_attachment(self, att: dict[str, Any]) -> MIMEBase:
        att_type = att["type"]
        if att_type == "file":
            return self._resolve_file_attachment(att["path"])
        elif att_type == "url":
            return self._resolve_url_attachment(att["url"], att["filename"])
        else:
            return self._resolve_provider_attachment(att)

    def trash_messages(self, message_ids: list[str]) -> dict[str, Any]:
        """Trash messages by IDs."""
        raise NotImplementedError(f"{self.provider} does not support trash_messages")

    def trash_by_query(self, query: str, max_results: int = 500) -> dict[str, Any]:
        """Trash messages matching a query."""
        raise NotImplementedError(f"{self.provider} does not support trash_by_query")

    def create_block_filter(self, sender: str) -> dict[str, Any]:
        """Create a filter to auto-delete from a sender."""
        raise NotImplementedError(f"{self.provider} does not support create_block_filter")

    def report_spam(self, message_ids: list[str]) -> dict[str, Any]:
        """Report messages as spam."""
        raise NotImplementedError(f"{self.provider} does not support report_spam")

    def get_contacts(self, max_results: int = 2000) -> list[dict[str, Any]]:
        """List contacts with email addresses."""
        raise NotImplementedError(f"{self.provider} does not support get_contacts")

    def extract_unsubscribe_link(self, message_id: str) -> dict[str, Any]:
        """Extract unsubscribe link from message headers."""
        raise NotImplementedError(f"{self.provider} does not support extract_unsubscribe_link")

    def create_label(self, name: str) -> dict[str, Any]:
        """Create a new label/folder."""
        raise NotImplementedError(f"{self.provider} does not support create_label")

    def _resolve_provider_attachment(self, att: dict[str, Any]) -> MIMEBase:
        raise NotImplementedError(
            f"Provider attachment type '{att.get('type')}' not supported by base EmailClient"
        )

    def _resolve_file_attachment(self, file_path: str) -> MIMEBase:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Attachment path does not exist: {file_path}")
        if path.suffix.lower() in BLOCKED_EXTENSIONS:
            raise ValueError(f"Blocked attachment type: {path.suffix}")
        data = path.read_bytes()
        if len(data) > MAX_ATTACHMENT_SIZE:
            size_mb = len(data) / (1024 * 1024)
            raise ValueError(f"Attachment exceeds 25MB limit: {path.name} ({size_mb:.1f}MB)")
        mime_type, _ = mimetypes.guess_type(str(path))
        mime_type = mime_type or "application/octet-stream"
        maintype, subtype = mime_type.split("/", 1)

        part: MIMEBase
        if maintype == "image":
            part = MIMEImage(data, _subtype=subtype)
        elif maintype == "audio":
            part = MIMEAudio(data, _subtype=subtype)
        elif maintype == "application":
            part = MIMEApplication(data, _subtype=subtype)
        else:
            part = MIMEBase(maintype, subtype)
            part.set_payload(data)

        part.add_header("Content-Disposition", "attachment", filename=path.name)
        return part

    def _resolve_url_attachment(self, url: str, filename: str) -> MIMEBase:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.content
        if len(data) > MAX_ATTACHMENT_SIZE:
            size_mb = len(data) / (1024 * 1024)
            raise ValueError(f"URL attachment exceeds 25MB limit: {filename} ({size_mb:.1f}MB)")
        content_type = resp.headers.get("Content-Type", "application/octet-stream")
        subtype = (
            content_type.split("/")[1].split(";")[0] if "/" in content_type else "octet-stream"
        )
        part = MIMEApplication(data, _subtype=subtype)
        part.add_header("Content-Disposition", "attachment", filename=filename)
        return part
