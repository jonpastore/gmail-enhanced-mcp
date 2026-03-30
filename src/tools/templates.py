from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..gmail_client import GmailClient

DEFAULT_TEMPLATE_DIR = Path("templates")


def _text_content(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


def _find_placeholders(text: str) -> set[str]:
    return set(re.findall(r"\{\{(\w+)\}\}", text))


def handle_save_template(
    args: dict[str, Any],
    client: GmailClient,
    template_dir: Path = DEFAULT_TEMPLATE_DIR,
) -> dict[str, Any]:
    name = args.get("name")
    if not name:
        raise ValueError("name is required")

    subject = args.get("subject", "")
    body = args.get("body", "")
    variables = args.get("variables", [])

    all_placeholders = _find_placeholders(subject) | _find_placeholders(body)
    declared = set(variables)
    undeclared = all_placeholders - declared
    if undeclared:
        raise ValueError(f"Placeholders {undeclared} not declared in variables list")

    template = {
        "name": name,
        "subject": subject,
        "body": body,
        "contentType": args.get("contentType", "text/plain"),
        "variables": variables,
    }

    template_dir.mkdir(parents=True, exist_ok=True)
    path = template_dir / f"{name}.json"
    path.write_text(json.dumps(template, indent=2))

    return _text_content(f"Template '{name}' saved to {path}")


def handle_use_template(
    args: dict[str, Any],
    client: GmailClient,
    template_dir: Path = DEFAULT_TEMPLATE_DIR,
) -> dict[str, Any]:
    name = args.get("name")
    if not name:
        raise ValueError("name is required")

    path = template_dir / f"{name}.json"
    if not path.exists():
        raise ValueError(f"Template not found: {name}")

    template = json.loads(path.read_text())
    variables = args.get("variables", {})
    required = set(template.get("variables", []))
    provided = set(variables.keys())
    missing = required - provided
    if missing:
        raise ValueError(f"Missing variables: {missing}")

    subject = template.get("subject", "")
    body = template.get("body", "")
    for key, value in variables.items():
        subject = subject.replace(f"{{{{{key}}}}}", value)
        body = body.replace(f"{{{{{key}}}}}", value)

    result = client.create_draft(
        to=args.get("to"),
        subject=subject,
        body=body,
        content_type=template.get("contentType", "text/plain"),
        cc=args.get("cc"),
        bcc=args.get("bcc"),
        attachments=args.get("attachments"),
    )

    return _text_content(
        f"Draft created from template '{name}'.\n"
        f"Draft ID: {result['id']}\n"
        f"Use gmail_send_draft with draftId '{result['id']}' to send."
    )
