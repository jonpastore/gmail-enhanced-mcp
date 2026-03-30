from __future__ import annotations

import base64
import mimetypes
from email.mime.application import MIMEApplication
from email.mime.audio import MIMEAudio
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Optional

import requests
from googleapiclient.discovery import build
from loguru import logger

from .auth import TokenManager
from .config import Config

BLOCKED_EXTENSIONS = {".exe", ".bat", ".cmd", ".scr", ".js", ".vbs", ".msi"}
MAX_ATTACHMENT_SIZE = 25 * 1024 * 1024


class GmailClient:
    def __init__(self, config: Config) -> None:
        self._token_mgr = TokenManager(config.client_secret_path, config.token_path)
        self._service: Any = None

    def _get_service(self) -> Any:
        if self._service is None:
            creds = self._token_mgr.get_credentials()
            self._service = build("gmail", "v1", credentials=creds)
        return self._service

    def get_profile(self) -> dict[str, Any]:
        svc = self._get_service()
        return svc.users().getProfile(userId="me").execute()

    def search_messages(
        self,
        q: str | None = None,
        max_results: int = 20,
        page_token: str | None = None,
        include_spam_trash: bool = False,
    ) -> dict[str, Any]:
        svc = self._get_service()
        kwargs: dict[str, Any] = {
            "userId": "me",
            "maxResults": max_results,
            "includeSpamTrash": include_spam_trash,
        }
        if q:
            kwargs["q"] = q
        if page_token:
            kwargs["pageToken"] = page_token
        result = svc.users().messages().list(**kwargs).execute()
        return {
            "messages": result.get("messages", []),
            "nextPageToken": result.get("nextPageToken"),
            "resultSizeEstimate": result.get("resultSizeEstimate", 0),
        }

    def read_message(self, message_id: str) -> dict[str, Any]:
        svc = self._get_service()
        return svc.users().messages().get(userId="me", id=message_id, format="full").execute()

    def read_thread(self, thread_id: str) -> dict[str, Any]:
        svc = self._get_service()
        return svc.users().threads().get(userId="me", id=thread_id, format="full").execute()

    def download_attachment(self, message_id: str, attachment_id: str, save_path: str) -> str:
        svc = self._get_service()
        att = svc.users().messages().attachments().get(
            userId="me", messageId=message_id, id=attachment_id
        ).execute()
        data = base64.urlsafe_b64decode(att["data"])
        path = Path(save_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        logger.info(f"Attachment saved: {len(data)} bytes")
        return str(path)

    def list_labels(self) -> list[dict[str, Any]]:
        svc = self._get_service()
        result = svc.users().labels().list(userId="me").execute()
        return result.get("labels", [])

    def modify_thread_labels(
        self,
        thread_id: str,
        add_label_ids: list[str] | None = None,
        remove_label_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        svc = self._get_service()
        body: dict[str, Any] = {}
        if add_label_ids:
            body["addLabelIds"] = add_label_ids
        if remove_label_ids:
            body["removeLabelIds"] = remove_label_ids
        return svc.users().threads().modify(userId="me", id=thread_id, body=body).execute()

    def list_drafts(self, max_results: int = 20, page_token: str | None = None) -> dict[str, Any]:
        svc = self._get_service()
        kwargs: dict[str, Any] = {"userId": "me", "maxResults": max_results}
        if page_token:
            kwargs["pageToken"] = page_token
        result = svc.users().drafts().list(**kwargs).execute()
        return {
            "drafts": result.get("drafts", []),
            "nextPageToken": result.get("nextPageToken"),
        }

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
        if attachments:
            msg = MIMEMultipart("mixed")
            text_part = MIMEText(body, "html" if content_type == "text/html" else "plain")
            msg.attach(text_part)
            for att in attachments:
                att_part = self._resolve_attachment(att)
                msg.attach(att_part)
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
        elif att_type == "gmail":
            return self._resolve_gmail_attachment(att["message_id"], att["attachment_id"])
        elif att_type == "url":
            return self._resolve_url_attachment(att["url"], att["filename"])
        else:
            raise ValueError(f"Unknown attachment type: {att_type}")

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

    def _resolve_gmail_attachment(self, message_id: str, attachment_id: str) -> MIMEBase:
        svc = self._get_service()
        att = svc.users().messages().attachments().get(
            userId="me", messageId=message_id, id=attachment_id
        ).execute()
        data = base64.urlsafe_b64decode(att["data"])
        msg = svc.users().messages().get(userId="me", id=message_id, format="full").execute()
        filename = self._find_attachment_filename(msg, attachment_id)
        mime_type, _ = mimetypes.guess_type(filename) if filename else (None, None)
        mime_type = mime_type or "application/octet-stream"
        maintype, subtype = mime_type.split("/", 1)
        part = MIMEApplication(data, _subtype=subtype)
        part.add_header("Content-Disposition", "attachment", filename=filename or "attachment")
        return part

    def _find_attachment_filename(self, message: dict[str, Any], attachment_id: str) -> str | None:
        for part in message.get("payload", {}).get("parts", []):
            body = part.get("body", {})
            if body.get("attachmentId") == attachment_id:
                return part.get("filename")
        return None

    def _resolve_url_attachment(self, url: str, filename: str) -> MIMEBase:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.content
        if len(data) > MAX_ATTACHMENT_SIZE:
            size_mb = len(data) / (1024 * 1024)
            raise ValueError(f"URL attachment exceeds 25MB limit: {filename} ({size_mb:.1f}MB)")
        content_type = resp.headers.get("Content-Type", "application/octet-stream")
        maintype = content_type.split("/")[0]
        subtype = content_type.split("/")[1].split(";")[0] if "/" in content_type else "octet-stream"
        part = MIMEApplication(data, _subtype=subtype)
        part.add_header("Content-Disposition", "attachment", filename=filename)
        return part

    def _encode_message(self, mime_msg: MIMEBase) -> str:
        return base64.urlsafe_b64encode(mime_msg.as_bytes()).decode("ascii")

    def create_draft(
        self, to: str | None = None, subject: str | None = None, body: str = "",
        content_type: str = "text/plain", cc: str | None = None, bcc: str | None = None,
        thread_id: str | None = None, attachments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        mime_msg = self.build_mime_message(
            to=to, subject=subject, body=body, content_type=content_type,
            cc=cc, bcc=bcc, thread_id=thread_id, attachments=attachments,
        )
        raw = self._encode_message(mime_msg)
        draft_body: dict[str, Any] = {"message": {"raw": raw}}
        if thread_id:
            draft_body["message"]["threadId"] = thread_id
        svc = self._get_service()
        return svc.users().drafts().create(userId="me", body=draft_body).execute()

    def update_draft(
        self, draft_id: str, to: str | None = None, subject: str | None = None,
        body: str = "", content_type: str = "text/plain", cc: str | None = None,
        bcc: str | None = None, attachments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        mime_msg = self.build_mime_message(
            to=to, subject=subject, body=body, content_type=content_type,
            cc=cc, bcc=bcc, attachments=attachments,
        )
        raw = self._encode_message(mime_msg)
        svc = self._get_service()
        return svc.users().drafts().update(
            userId="me", id=draft_id, body={"message": {"raw": raw}}
        ).execute()

    def send_draft(self, draft_id: str) -> dict[str, Any]:
        svc = self._get_service()
        return svc.users().drafts().send(userId="me", body={"id": draft_id}).execute()

    def send_email(
        self, to: str, subject: str, body: str, content_type: str = "text/plain",
        cc: str | None = None, bcc: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        mime_msg = self.build_mime_message(
            to=to, subject=subject, body=body, content_type=content_type,
            cc=cc, bcc=bcc, attachments=attachments,
        )
        raw = self._encode_message(mime_msg)
        svc = self._get_service()
        return svc.users().messages().send(userId="me", body={"raw": raw}).execute()
