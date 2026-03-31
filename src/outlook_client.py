from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import requests
from loguru import logger

from .auth import MicrosoftTokenManager
from .email_client import EmailClient
from .outlook_query import translate_gmail_query

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


class OutlookClient(EmailClient):
    def __init__(self, token_manager: MicrosoftTokenManager, account_email: str) -> None:
        self._token_mgr = token_manager
        self._account_email = account_email

    @property
    def email_address(self) -> str:
        return self._account_email

    @property
    def provider(self) -> str:
        return "outlook"

    def _graph_get(self, path: str, params: dict | None = None) -> dict:
        token = self._token_mgr.get_token()
        resp = requests.get(
            f"{GRAPH_BASE}{path}",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def _graph_post(self, path: str, json_body: dict | None = None) -> requests.Response:
        token = self._token_mgr.get_token()
        resp = requests.post(
            f"{GRAPH_BASE}{path}",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=json_body,
            timeout=30,
        )
        resp.raise_for_status()
        return resp

    def _graph_patch(self, path: str, json_body: dict) -> dict:
        token = self._token_mgr.get_token()
        resp = requests.patch(
            f"{GRAPH_BASE}{path}",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=json_body,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def get_profile(self) -> dict[str, Any]:
        data = self._graph_get("/me")
        return {
            "emailAddress": data.get("mail") or data.get("userPrincipalName", ""),
            "messagesTotal": data.get("messagesTotal", 0),
            "threadsTotal": data.get("threadsTotal", 0),
            "historyId": "",
        }

    def search_messages(
        self,
        q: str | None = None,
        max_results: int = 20,
        page_token: str | None = None,
        include_spam_trash: bool = False,
    ) -> dict[str, Any]:
        parts = translate_gmail_query(q)
        params: dict[str, Any] = {"$top": max_results}
        if parts.filter:
            params["$filter"] = parts.filter
        if parts.search:
            params["$search"] = f'"{parts.search}"'
        if page_token:
            params["$skip"] = page_token

        path = f"/me/mailFolders/{parts.folder}/messages" if parts.folder else "/me/messages"
        data = self._graph_get(path, params)

        messages = [
            {"id": m["id"], "threadId": m.get("conversationId", m["id"])}
            for m in data.get("value", [])
        ]
        next_link = data.get("@odata.nextLink")
        next_token = None
        if next_link and "$skip=" in next_link:
            next_token = next_link.split("$skip=")[1].split("&")[0]

        return {
            "messages": messages,
            "nextPageToken": next_token,
            "resultSizeEstimate": data.get("@odata.count", len(messages)),
        }

    def read_message(self, message_id: str) -> dict[str, Any]:
        msg = self._graph_get(f"/me/messages/{message_id}")
        return self._normalize_message(msg)

    def read_thread(self, thread_id: str) -> dict[str, Any]:
        data = self._graph_get(
            "/me/messages",
            params={
                "$filter": f"conversationId eq '{thread_id}'",
                "$orderby": "receivedDateTime",
            },
        )
        messages = [self._normalize_message(m) for m in data.get("value", [])]
        return {
            "id": thread_id,
            "messages": messages,
            "historyId": "",
        }

    def download_attachment(self, message_id: str, attachment_id: str, save_path: str) -> str:
        data = self._graph_get(f"/me/messages/{message_id}/attachments/{attachment_id}")
        content_bytes = base64.b64decode(data.get("contentBytes", ""))
        path = Path(save_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content_bytes)
        logger.info(f"Attachment saved: {len(content_bytes)} bytes")
        return str(path)

    def list_labels(self) -> list[dict[str, Any]]:
        folders = self._graph_get("/me/mailFolders")
        categories = self._graph_get("/me/outlook/masterCategories")
        result: list[dict[str, Any]] = []
        for f in folders.get("value", []):
            result.append(
                {
                    "id": f["id"],
                    "name": f["displayName"],
                    "type": "system",
                }
            )
        for c in categories.get("value", []):
            result.append(
                {
                    "id": c.get("id", c["displayName"]),
                    "name": c["displayName"],
                    "type": "user",
                }
            )
        return result

    def modify_thread_labels(
        self,
        thread_id: str,
        add_label_ids: list[str] | None = None,
        remove_label_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        thread_data = self._graph_get(
            "/me/messages",
            params={"$filter": f"conversationId eq '{thread_id}'", "$select": "id"},
        )
        msg_ids = [m["id"] for m in thread_data.get("value", [])]

        for msg_id in msg_ids:
            patch_body: dict[str, Any] = {}
            if add_label_ids:
                for label in add_label_ids:
                    if label == "UNREAD":
                        patch_body["isRead"] = False
                    elif label == "STARRED":
                        patch_body["flag"] = {"flagStatus": "flagged"}
                    else:
                        existing = self._graph_get(
                            f"/me/messages/{msg_id}", {"$select": "categories"}
                        )
                        cats = list(existing.get("categories", []))
                        if label not in cats:
                            cats.append(label)
                        patch_body["categories"] = cats
            if remove_label_ids:
                for label in remove_label_ids:
                    if label == "UNREAD":
                        patch_body["isRead"] = True
                    elif label == "STARRED":
                        patch_body["flag"] = {"flagStatus": "notFlagged"}
                    else:
                        existing = self._graph_get(
                            f"/me/messages/{msg_id}", {"$select": "categories"}
                        )
                        cats = [c for c in existing.get("categories", []) if c != label]
                        patch_body["categories"] = cats
            if patch_body:
                self._graph_patch(f"/me/messages/{msg_id}", patch_body)

        return {"id": thread_id, "messages": msg_ids}

    def list_drafts(self, max_results: int = 20, page_token: str | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"$top": max_results}
        if page_token:
            params["$skip"] = page_token
        data = self._graph_get("/me/mailFolders/drafts/messages", params)
        drafts = [
            {"id": m["id"], "message": {"id": m["id"], "threadId": m.get("conversationId", "")}}
            for m in data.get("value", [])
        ]
        return {
            "drafts": drafts,
            "nextPageToken": None,
        }

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
        msg_body = self._build_graph_message(to, subject, body, content_type, cc, bcc, thread_id)
        resp = self._graph_post("/me/messages", msg_body)
        draft = resp.json()
        draft_id = draft["id"]

        graph_atts = self._build_graph_attachments(attachments)
        for att in graph_atts:
            self._graph_post(f"/me/messages/{draft_id}/attachments", att)

        return {"id": draft_id, "message": {"id": draft_id}}

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
        msg_body = self._build_graph_message(to, subject, body, content_type, cc, bcc)
        result = self._graph_patch(f"/me/messages/{draft_id}", msg_body)

        graph_atts = self._build_graph_attachments(attachments)
        for att in graph_atts:
            self._graph_post(f"/me/messages/{draft_id}/attachments", att)

        return result

    def send_draft(self, draft_id: str) -> dict[str, Any]:
        self._graph_post(f"/me/messages/{draft_id}/send")
        return {"id": draft_id, "status": "sent"}

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
        message = self._build_graph_message(to, subject, body, content_type, cc, bcc)
        graph_atts = self._build_graph_attachments(attachments)
        if graph_atts:
            message["attachments"] = graph_atts
        send_body = {"message": message, "saveToSentItems": True}
        self._graph_post("/me/sendMail", send_body)
        return {"status": "sent"}

    def _build_graph_message(
        self,
        to: str | None = None,
        subject: str | None = None,
        body: str = "",
        content_type: str = "text/plain",
        cc: str | None = None,
        bcc: str | None = None,
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        msg: dict[str, Any] = {
            "body": {
                "contentType": "HTML" if content_type == "text/html" else "Text",
                "content": body,
            },
        }
        if subject is not None:
            msg["subject"] = subject
        if to:
            msg["toRecipients"] = self._parse_recipients(to)
        if cc:
            msg["ccRecipients"] = self._parse_recipients(cc)
        if bcc:
            msg["bccRecipients"] = self._parse_recipients(bcc)
        if thread_id:
            msg["conversationId"] = thread_id
        return msg

    def _parse_recipients(self, addr_str: str) -> list[dict[str, Any]]:
        return [{"emailAddress": {"address": a.strip()}} for a in addr_str.split(",") if a.strip()]

    def _build_graph_attachments(
        self, attachments: list[dict[str, Any]] | None
    ) -> list[dict[str, Any]]:
        if not attachments:
            return []
        result = []
        for att in attachments:
            mime_part = self._resolve_attachment(att)
            payload = mime_part.get_payload(decode=True)
            filename = mime_part.get_filename() or "attachment"
            att_content_type = mime_part.get_content_type()
            result.append(
                {
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": filename,
                    "contentType": att_content_type,
                    "contentBytes": base64.b64encode(payload).decode() if payload else "",
                }
            )
        return result

    def _normalize_message(self, msg: dict) -> dict[str, Any]:
        headers: list[dict[str, str]] = []
        if msg.get("from"):
            addr = msg["from"]["emailAddress"]
            headers.append({"name": "From", "value": f"{addr.get('name', '')} <{addr['address']}>"})
        to_addrs = ", ".join(
            f"{r['emailAddress'].get('name', '')} <{r['emailAddress']['address']}>"
            for r in msg.get("toRecipients", [])
        )
        if to_addrs:
            headers.append({"name": "To", "value": to_addrs})
        cc_addrs = ", ".join(
            f"{r['emailAddress'].get('name', '')} <{r['emailAddress']['address']}>"
            for r in msg.get("ccRecipients", [])
        )
        if cc_addrs:
            headers.append({"name": "Cc", "value": cc_addrs})
        headers.append({"name": "Subject", "value": msg.get("subject", "")})
        headers.append({"name": "Date", "value": msg.get("receivedDateTime", "")})

        body_content = msg.get("body", {}).get("content", "")
        body_type = msg.get("body", {}).get("contentType", "text")
        body_data = base64.urlsafe_b64encode(body_content.encode()).decode()

        label_ids: list[str] = []
        if not msg.get("isRead", True):
            label_ids.append("UNREAD")
        if msg.get("flag", {}).get("flagStatus") == "flagged":
            label_ids.append("STARRED")

        return {
            "id": msg["id"],
            "threadId": msg.get("conversationId", msg["id"]),
            "labelIds": label_ids,
            "snippet": body_content[:100] if body_content else "",
            "payload": {
                "mimeType": f"text/{'html' if body_type == 'html' else 'plain'}",
                "headers": headers,
                "body": {"data": body_data, "size": len(body_content)},
                "parts": [],
            },
            "sizeEstimate": msg.get("size", 0),
            "internalDate": msg.get("receivedDateTime", ""),
        }
