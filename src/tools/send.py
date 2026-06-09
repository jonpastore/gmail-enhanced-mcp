from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ..handler_context import HandlerContext
from .response import text_content as _text_content


def _load_signature(account: str) -> dict | None:
    """Load the per-account outbound signature for `account` from a signatures.json
    that the install step places on the box (gitignored user PII — never in git).

    Returns the account's signature dict only when it exists AND has auto_append=true.
    Profile-gating is structural: regulated/home customer boxes ship no signatures
    file (or no entry), so nothing is appended there. Never raises."""
    if not account:
        return None
    try:
        override = os.environ.get("EMAIL_SIGNATURES_FILE")
        candidates = (
            [Path(override)]
            if override
            else [
                Path.home() / "gmail-enhanced-mcp" / "signatures.json",
                Path(__file__).resolve().parents[2] / "signatures.json",
            ]
        )
        for p in candidates:
            if p.is_file():
                data = json.loads(p.read_text())
                acct = (data.get("accounts") or {}).get(account)
                if acct and acct.get("auto_append"):
                    return acct
                return None
    except Exception:
        return None
    return None


def _apply_signature(body: str, content_type: str, sig: dict) -> str:
    """Idempotently append the signature. If the marker text is already present
    (e.g. a reply quoting a previously-signed message), leave the body unchanged."""
    marker = sig.get("marker") or ""
    if marker and marker in body:
        return body
    if "html" in (content_type or "").lower():
        html = sig.get("html") or ""
        return f"{body}<br><br>{html}" if html else body
    text = sig.get("text") or ""
    return f"{body}\n\n{text}" if text else body


def handle_send_email(args: dict[str, Any], ctx: HandlerContext) -> dict[str, Any]:
    to = args.get("to")
    if not to:
        raise ValueError("to is required")
    body = args.get("body")
    if not body:
        raise ValueError("body is required")
    content_type = args.get("contentType", "text/plain")

    # Auto-append the owner's signature for the sending account (idempotent). Driven
    # purely by the presence of a signatures.json entry with auto_append=true, so it
    # is on for the founder's accounts and off everywhere a signatures file isn't shipped.
    try:
        sig = _load_signature(getattr(ctx.client, "email_address", "") or "")
        if sig:
            body = _apply_signature(body, content_type, sig)
    except Exception:
        pass  # signature logic must never break a send

    result = ctx.client.send_email(
        to=to,
        subject=args.get("subject", ""),
        body=body,
        content_type=content_type,
        cc=args.get("cc"),
        bcc=args.get("bcc"),
        attachments=args.get("attachments"),
    )
    return _text_content(
        f"Email sent successfully.\nMessage ID: {result.get('id', '(sent)')}\n"
        f"Labels: {', '.join(result.get('labelIds', []))}"
    )
