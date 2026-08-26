"""Parse List-Unsubscribe headers and execute RFC 8058 one-click POST.

Does not call Gmail or Graph APIs. Does not log URLs (they can carry tokens).
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests

_LINK_RE = re.compile(r"<([^>]+)>")


def parse_unsubscribe_headers(headers: list[dict[str, Any]]) -> dict[str, Any]:
    """Parse List-Unsubscribe and List-Unsubscribe-Post from message headers.

    Args:
        headers: Gmail/Graph-style ``{name, value}`` header dicts.

    Returns:
        Dict with found, unsubscribe_url, unsubscribe_mailto, one_click.
    """
    unsub_header = ""
    post_header = ""
    for header in headers:
        name = str(header.get("name", "")).lower()
        value = str(header.get("value", ""))
        if name == "list-unsubscribe":
            unsub_header = value
        elif name == "list-unsubscribe-post":
            post_header = value
    if not unsub_header:
        return {
            "found": False,
            "unsubscribe_url": None,
            "unsubscribe_mailto": None,
            "one_click": False,
        }
    url: str | None = None
    mailto: str | None = None
    links = _LINK_RE.findall(unsub_header)
    if not links:
        stripped = unsub_header.strip()
        links = [stripped] if stripped else []
    for link in links:
        if link.startswith("https://") or link.startswith("http://"):
            url = link
        elif link.startswith("mailto:"):
            mailto = link
    return {
        "found": bool(url or mailto),
        "unsubscribe_url": url,
        "unsubscribe_mailto": mailto,
        "one_click": "one-click" in post_header.lower(),
    }


def parse_mailto(mailto: str) -> tuple[str, str]:
    """Split a mailto: unsubscribe URI into address and subject.

    Args:
        mailto: mailto URI from List-Unsubscribe.

    Returns:
        (to_address, subject).
    """
    parsed = urlparse(mailto)
    to_addr = parsed.path
    subject_vals = parse_qs(parsed.query).get("subject", [])
    subject = subject_vals[0] if subject_vals else "unsubscribe"
    return to_addr, subject


def execute_one_click(url: str) -> dict[str, Any]:
    """POST RFC 8058 one-click body to an HTTPS unsubscribe URL.

    Args:
        url: HTTPS List-Unsubscribe URL.

    Returns:
        Dict with method and HTTP status.

    Raises:
        ValueError: If the URL is not HTTPS.
        RuntimeError: If the POST returns HTTP 400+.
    """
    if not url.startswith("https://"):
        raise ValueError("Unsubscribe URL must be HTTPS")
    response = requests.post(
        url,
        data="List-Unsubscribe=One-Click",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=15,
        allow_redirects=False,
    )
    if response.status_code >= 400:
        raise RuntimeError("Unsubscribe request failed")
    return {"method": "one_click", "status": response.status_code}
