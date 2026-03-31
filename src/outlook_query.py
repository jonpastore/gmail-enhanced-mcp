from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


@dataclass
class QueryParts:
    search: str = ""
    filter: str = ""
    folder: str | None = None


FOLDER_MAP = {
    "inbox": "inbox",
    "sent": "sentitems",
    "drafts": "drafts",
    "trash": "deleteditems",
    "spam": "junkemail",
    "junk": "junkemail",
}

FILTER_OPERATORS = {
    "is:unread": "isRead eq false",
    "is:read": "isRead eq true",
    "is:starred": "flag/flagStatus eq 'flagged'",
    "has:attachment": "hasAttachments eq true",
}


def translate_gmail_query(q: str | None) -> QueryParts:
    if not q:
        return QueryParts()

    parts = QueryParts()
    filters: list[str] = []
    search_parts: list[str] = []
    tokens = _tokenize(q)

    for token in tokens:
        if token in FILTER_OPERATORS:
            filters.append(FILTER_OPERATORS[token])
        elif token.startswith("in:"):
            folder_name = token[3:]
            parts.folder = FOLDER_MAP.get(folder_name, folder_name)
        elif token.startswith("after:"):
            date_str = _parse_date(token[6:])
            filters.append(f"receivedDateTime ge {date_str}T00:00:00Z")
        elif token.startswith("before:"):
            date_str = _parse_date(token[7:])
            filters.append(f"receivedDateTime lt {date_str}T00:00:00Z")
        elif token.startswith("newer_than:"):
            days = _parse_relative_date(token[11:])
            dt = datetime.now(UTC) - timedelta(days=days)
            filters.append(f"receivedDateTime ge {dt.strftime('%Y-%m-%d')}T00:00:00Z")
        elif token.startswith("label:"):
            label = token[6:]
            filters.append(f"categories/any(c:c eq '{label}')")
        elif token.startswith("-"):
            search_parts.append(f"NOT {token[1:]}")
        else:
            search_parts.append(token)

    parts.search = " ".join(search_parts)
    parts.filter = " and ".join(filters)
    return parts


def _tokenize(q: str) -> list[str]:
    tokens: list[str] = []
    i = 0
    while i < len(q):
        if q[i] == '"':
            end_idx = q.find('"', i + 1)
            if end_idx == -1:
                end_idx = len(q) - 1
            tokens.append(q[i : end_idx + 1])
            i = end_idx + 1
        elif q[i] == " ":
            i += 1
        else:
            space_idx = q.find(" ", i)
            if space_idx == -1:
                space_idx = len(q)
            tokens.append(q[i:space_idx])
            i = space_idx
    return tokens


def _parse_date(date_str: str) -> str:
    parts = date_str.replace("-", "/").split("/")
    if len(parts) == 3:
        year, month, day = parts[0], parts[1].zfill(2), parts[2].zfill(2)
        return f"{year}-{month}-{day}"
    return date_str


def _parse_relative_date(spec: str) -> int:
    match = re.match(r"(\d+)([dhm])", spec)
    if not match:
        return 7
    value, unit = int(match.group(1)), match.group(2)
    if unit == "d":
        return value
    elif unit == "h":
        return max(1, value // 24)
    elif unit == "m":
        return value * 30
    return value
