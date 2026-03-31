from __future__ import annotations

import base64
import mimetypes
from email.mime.application import MIMEApplication
from email.mime.base import MIMEBase
from typing import Any

from googleapiclient.discovery import build
from loguru import logger

from .auth import TokenManager
from .email_client import EmailClient


class GmailClient(EmailClient):
    def __init__(self, token_manager: TokenManager, account_email: str) -> None:
        self._token_mgr = token_manager
        self._account_email = account_email
        self._service: Any = None

    @property
    def email_address(self) -> str:
        return self._account_email

    @property
    def provider(self) -> str:
        return "gmail"

    def _get_service(self) -> Any:
        if self._service is None:
            creds = self._token_mgr.get_credentials()
            self._service = build("gmail", "v1", credentials=creds)
        return self._service

    def get_profile(self) -> dict[str, Any]:
        svc = self._get_service()
        return svc.users().getProfile(userId="me").execute()  # type: ignore[no-any-return]

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
        return svc.users().messages().get(userId="me", id=message_id, format="full").execute()  # type: ignore[no-any-return]

    def read_thread(self, thread_id: str) -> dict[str, Any]:
        svc = self._get_service()
        return svc.users().threads().get(userId="me", id=thread_id, format="full").execute()  # type: ignore[no-any-return]

    def download_attachment(self, message_id: str, attachment_id: str, save_path: str) -> str:
        svc = self._get_service()
        att = (
            svc.users()
            .messages()
            .attachments()
            .get(userId="me", messageId=message_id, id=attachment_id)
            .execute()
        )
        data = base64.urlsafe_b64decode(att["data"])
        from pathlib import Path

        path = Path(save_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        logger.info(f"Attachment saved: {len(data)} bytes")
        return str(path)

    def list_labels(self) -> list[dict[str, Any]]:
        svc = self._get_service()
        result = svc.users().labels().list(userId="me").execute()
        return result.get("labels", [])  # type: ignore[no-any-return]

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
        return svc.users().threads().modify(userId="me", id=thread_id, body=body).execute()  # type: ignore[no-any-return]

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

    def _resolve_provider_attachment(self, att: dict[str, Any]) -> MIMEBase:
        att_type = att.get("type")
        if att_type == "gmail":
            return self._resolve_gmail_attachment(att["message_id"], att["attachment_id"])
        raise ValueError(f"Unknown attachment type: {att_type}")

    def _resolve_gmail_attachment(self, message_id: str, attachment_id: str) -> MIMEBase:
        svc = self._get_service()
        att = (
            svc.users()
            .messages()
            .attachments()
            .get(userId="me", messageId=message_id, id=attachment_id)
            .execute()
        )
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
                return part.get("filename")  # type: ignore[no-any-return]
        return None

    def _encode_message(self, mime_msg: MIMEBase) -> str:
        return base64.urlsafe_b64encode(mime_msg.as_bytes()).decode("ascii")

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
    ) -> dict[str, Any]:
        mime_msg = self.build_mime_message(
            to=to,
            subject=subject,
            body=body,
            content_type=content_type,
            cc=cc,
            bcc=bcc,
            thread_id=thread_id,
            attachments=attachments,
        )
        raw = self._encode_message(mime_msg)
        draft_body: dict[str, Any] = {"message": {"raw": raw}}
        if thread_id:
            draft_body["message"]["threadId"] = thread_id
        svc = self._get_service()
        return svc.users().drafts().create(userId="me", body=draft_body).execute()  # type: ignore[no-any-return]

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
    ) -> dict[str, Any]:
        mime_msg = self.build_mime_message(
            to=to,
            subject=subject,
            body=body,
            content_type=content_type,
            cc=cc,
            bcc=bcc,
            attachments=attachments,
        )
        raw = self._encode_message(mime_msg)
        svc = self._get_service()
        return (  # type: ignore[no-any-return]
            svc.users()
            .drafts()
            .update(userId="me", id=draft_id, body={"message": {"raw": raw}})
            .execute()
        )

    def send_draft(self, draft_id: str) -> dict[str, Any]:
        svc = self._get_service()
        return svc.users().drafts().send(userId="me", body={"id": draft_id}).execute()  # type: ignore[no-any-return]

    def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        content_type: str = "text/plain",
        cc: str | None = None,
        bcc: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        mime_msg = self.build_mime_message(
            to=to,
            subject=subject,
            body=body,
            content_type=content_type,
            cc=cc,
            bcc=bcc,
            attachments=attachments,
        )
        raw = self._encode_message(mime_msg)
        svc = self._get_service()
        return svc.users().messages().send(userId="me", body={"raw": raw}).execute()  # type: ignore[no-any-return]
