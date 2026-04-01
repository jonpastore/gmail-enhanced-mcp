from __future__ import annotations

import base64
import mimetypes
from email.mime.application import MIMEApplication
from email.mime.base import MIMEBase
from typing import Any, Protocol, runtime_checkable

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from loguru import logger

from .auth import TokenManager
from .email_client import EmailClient


@runtime_checkable
class SyncProvider(Protocol):
    """Protocol for provider-specific incremental sync.

    NOT part of EmailClient ABC -- keeps it clean.
    """

    def history_sync(
        self,
        start_history_id: str,
        max_results: int = 100,
    ) -> dict[str, Any]: ...


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

    def reset_service(self) -> None:
        """Force rebuild of the Gmail API service on next call."""
        self._service = None

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

    def history_sync(
        self,
        start_history_id: str,
        max_results: int = 100,
    ) -> dict[str, Any]:
        """Fetch changes since a historyId using Gmail history.list API.

        Args:
            start_history_id: The historyId to start syncing from.
            max_results: Maximum number of history records per page.

        Returns:
            Dict with keys: history_id, added, deleted, label_changes.
            If historyId is expired (404), returns full_sync_required: True.
        """
        svc = self._get_service()
        added: list[str] = []
        deleted: list[str] = []
        label_changes: list[dict[str, Any]] = []
        history_id = start_history_id
        page_token: str | None = None

        try:
            while True:
                kwargs: dict[str, Any] = {
                    "userId": "me",
                    "startHistoryId": start_history_id,
                    "maxResults": max_results,
                }
                if page_token:
                    kwargs["pageToken"] = page_token

                result = svc.users().history().list(**kwargs).execute()
                history_id = result.get("historyId", history_id)

                for entry in result.get("history", []):
                    for item in entry.get("messagesAdded", []):
                        added.append(item["message"]["id"])
                    for item in entry.get("messagesDeleted", []):
                        deleted.append(item["message"]["id"])
                    for item in entry.get("labelsAdded", []):
                        label_changes.append(
                            {
                                "message_id": item["message"]["id"],
                                "action": "added",
                                "label_ids": item["labelIds"],
                            }
                        )
                    for item in entry.get("labelsRemoved", []):
                        label_changes.append(
                            {
                                "message_id": item["message"]["id"],
                                "action": "removed",
                                "label_ids": item["labelIds"],
                            }
                        )

                page_token = result.get("nextPageToken")
                if not page_token:
                    break

        except HttpError as exc:
            if exc.resp.status == 404:  # type: ignore[union-attr]
                logger.warning("History ID expired, full sync required")
                return {
                    "full_sync_required": True,
                    "added": [],
                    "deleted": [],
                    "label_changes": [],
                }
            raise

        return {
            "history_id": history_id,
            "added": added,
            "deleted": deleted,
            "label_changes": label_changes,
        }

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

    def extract_unsubscribe_link(self, message_id: str) -> dict[str, Any]:
        """Extract List-Unsubscribe header from a message.

        Args:
            message_id: The message ID to inspect.

        Returns:
            Dict with found, unsubscribe_url, unsubscribe_mailto.
        """
        import re

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

        links = re.findall(r"<([^>]+)>", unsub_header)
        url: str | None = None
        mailto: str | None = None
        for link in links:
            if link.startswith("https://") or link.startswith("http://"):
                url = link
            elif link.startswith("mailto:"):
                mailto = link
        return {"found": True, "unsubscribe_url": url, "unsubscribe_mailto": mailto}

    def create_label(self, name: str) -> dict[str, Any]:
        """Create a new Gmail label.

        Args:
            name: Label name to create.

        Returns:
            Dict with id and name of the created label.
        """
        svc = self._get_service()
        label_body = {
            "name": name,
            "labelListVisibility": "labelShow",
            "messageListVisibility": "show",
        }
        result = svc.users().labels().create(userId="me", body=label_body).execute()
        logger.info(f"Created label: {result.get('name')} ({result.get('id')})")
        return {"id": result["id"], "name": result["name"]}
