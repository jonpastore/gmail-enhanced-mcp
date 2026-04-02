from __future__ import annotations

import base64
import re
from typing import Any

from dateutil import parser as dateutil_parser
from pydantic import BaseModel


class TripSegment(BaseModel):
    """A single travel booking segment."""

    type: str
    provider: str
    confirmation_number: str | None = None
    start_date: str
    end_date: str | None = None
    details: str
    source_message_id: str


class Itinerary(BaseModel):
    """Collection of parsed travel segments."""

    trips: list[TripSegment] = []


def _decode_body(body: dict[str, Any]) -> str:
    data = body.get("data", "")
    if not data:
        return ""
    try:
        return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
    except Exception:
        return ""


def _find_body_part(parts: list[dict[str, Any]], mime_type: str) -> str:
    """Recursively search parts tree for a body with the given MIME type."""
    for part in parts:
        if part.get("mimeType") == mime_type:
            text = _decode_body(part.get("body", {}))
            if text:
                return text
        sub_parts = part.get("parts", [])
        if sub_parts:
            text = _find_body_part(sub_parts, mime_type)
            if text:
                return text
    return ""


def _extract_body(payload: dict[str, Any]) -> str:
    """Extract body text from payload, recursing into nested multipart."""
    parts = payload.get("parts", [])
    if parts:
        text = _find_body_part(parts, "text/plain")
        if not text:
            text = _find_body_part(parts, "text/html")
        return text
    return _decode_body(payload.get("body", {}))


class ItineraryParser:
    """Extract travel bookings from email messages."""

    FLIGHT_SENDERS = re.compile(
        r"(airline|airlines|airways|pacific|philippine|cebu|delta|united|american"
        r"|southwest|jetblue|esky|expedia|orbitz|kayak|booking\.com)",
        re.IGNORECASE,
    )
    HOTEL_SENDERS = re.compile(
        r"(hotel|resort|inn|marriott|hilton|hyatt|airbnb|agoda|orbitz"
        r"|expedia|booking\.com|vrbo)",
        re.IGNORECASE,
    )
    CAR_SENDERS = re.compile(
        r"(hertz|avis|enterprise|sixt|budget|national)",
        re.IGNORECASE,
    )

    CONFIRMATION_PATTERNS = [
        re.compile(r"(?:PNR|Record Locator)[:\s]*([A-Z0-9]{6})", re.IGNORECASE),
        re.compile(
            r"(?:Confirmation|Booking)\s*(?:#|Number|No\.?)[:\s]*([A-Z0-9\-]+)",
            re.IGNORECASE,
        ),
        re.compile(r"(?:Itinerary)\s*(?:#|Number)[:\s]*(\d+)", re.IGNORECASE),
        re.compile(
            r"(?:Reservation)\s*(?:#|ID|Number)[:\s]*([A-Z0-9\-]+)",
            re.IGNORECASE,
        ),
    ]
    FLIGHT_NUMBER = re.compile(r"\b([A-Z]{2})\s*(\d{2,4})\b")
    ROUTE_PATTERN = re.compile(r"\b([A-Z]{3})\s*(?:→|->|to|–|-)\s*([A-Z]{3})\b", re.IGNORECASE)

    _DATE_PATTERNS = [
        re.compile(r"\b(\d{4}-\d{2}-\d{2})\b"),
        re.compile(r"\b(\d{2}/\d{2}/\d{4})\b"),
        re.compile(
            r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?"
            r"|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?"
            r"|Dec(?:ember)?)\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s*(\d{4}))?\b",
            re.IGNORECASE,
        ),
    ]

    def parse_messages(self, messages: list[dict[str, Any]]) -> Itinerary:
        """Parse a list of Gmail message dicts into an Itinerary.

        Args:
            messages: List of Gmail API message resource dicts.

        Returns:
            Itinerary containing deduplicated TripSegment instances.
        """
        trips: list[TripSegment] = []
        for msg in messages:
            headers = self._extract_headers(msg)
            from_addr = headers.get("from", "")
            subject = headers.get("subject", "")
            msg_type = self._classify_message(from_addr, subject)
            if msg_type == "unknown":
                continue
            segment = self._extract_segment(msg, msg_type)
            trips.append(segment)
        return Itinerary(trips=self._dedup_trips(trips))

    def _extract_headers(self, msg: dict[str, Any]) -> dict[str, str]:
        payload = msg.get("payload", {})
        raw_headers = payload.get("headers", [])
        return {h["name"].lower(): h["value"] for h in raw_headers}

    def _classify_message(self, from_addr: str, subject: str) -> str:
        """Classify a message as flight, hotel, car_rental, or unknown.

        Args:
            from_addr: The From header value.
            subject: The Subject header value.

        Returns:
            One of "flight", "hotel", "car_rental", or "unknown".
        """
        combined = f"{from_addr} {subject}"
        if self.CAR_SENDERS.search(combined):
            return "car_rental"
        if self.FLIGHT_SENDERS.search(combined):
            return "hotel" if self.HOTEL_SENDERS.search(combined) else "flight"
        if self.HOTEL_SENDERS.search(combined):
            return "hotel"
        return "unknown"

    def _extract_segment(self, msg: dict[str, Any], msg_type: str) -> TripSegment:
        """Extract a TripSegment from a classified Gmail message dict.

        Args:
            msg: Gmail API message resource dict.
            msg_type: One of "flight", "hotel", or "car_rental".

        Returns:
            A populated TripSegment instance.
        """
        headers = self._extract_headers(msg)
        from_addr = headers.get("from", "")
        subject = headers.get("subject", "")
        msg_id = msg.get("id", "")

        payload = msg.get("payload", {})
        body = _extract_body(payload)
        text = f"{subject}\n{body}"

        provider = self._extract_provider(from_addr, subject)
        confirmation = self._extract_confirmation(text)
        start_date = self._extract_date_from_text(text) or ""

        if msg_type == "flight":
            details = self._extract_flight_details(text)
            end_date = None
        elif msg_type == "hotel":
            details = self._extract_hotel_details(text, subject)
            end_date = self._extract_end_date(text, start_date)
        else:
            details = subject
            end_date = self._extract_end_date(text, start_date)

        return TripSegment(
            type=msg_type,
            provider=provider,
            confirmation_number=confirmation,
            start_date=start_date,
            end_date=end_date,
            details=details,
            source_message_id=msg_id,
        )

    def _extract_provider(self, from_addr: str, subject: str) -> str:
        """Derive a human-readable provider name from the From address or subject.

        Args:
            from_addr: The From header value.
            subject: The Subject header value.

        Returns:
            A provider name string, falling back to the domain or "Unknown".
        """
        display_match = re.search(r"^([^<]+)<", from_addr)
        if display_match:
            name = display_match.group(1).strip().strip('"')
            if name:
                return name
        domain_match = re.search(r"@([\w.\-]+)", from_addr)
        if domain_match:
            domain = domain_match.group(1)
            parts = domain.rsplit(".", 2)
            return parts[-2].capitalize() if len(parts) >= 2 else domain
        return "Unknown"

    def _extract_confirmation(self, text: str) -> str | None:
        """Search text for a booking confirmation or PNR number.

        Args:
            text: Combined subject and body text.

        Returns:
            The first matched confirmation string, or None.
        """
        for pattern in self.CONFIRMATION_PATTERNS:
            match = pattern.search(text)
            if match:
                return match.group(1).strip()
        return None

    def _extract_date_from_text(self, text: str) -> str | None:
        """Find the first recognisable date in text using dateutil.

        Args:
            text: Text to search for date expressions.

        Returns:
            ISO date string (YYYY-MM-DD) or None if no date found.
        """
        for pattern in self._DATE_PATTERNS:
            match = pattern.search(text)
            if match:
                try:
                    raw = match.group(0)
                    parsed = dateutil_parser.parse(raw, fuzzy=True)
                    return parsed.date().isoformat()
                except Exception:
                    continue
        return None

    def _extract_end_date(self, text: str, start_date: str) -> str | None:
        """Find a second date in text that follows the start date.

        Args:
            text: Text to search for date expressions.
            start_date: ISO date string of the already-found start date.

        Returns:
            ISO date string for checkout/return date, or None.
        """
        dates: list[str] = []
        for pattern in self._DATE_PATTERNS:
            for match in pattern.finditer(text):
                try:
                    raw = match.group(0)
                    parsed = dateutil_parser.parse(raw, fuzzy=True)
                    iso = parsed.date().isoformat()
                    if iso not in dates:
                        dates.append(iso)
                except Exception:
                    continue
        dates_after = [d for d in dates if d > start_date]
        return dates_after[0] if dates_after else None

    def _extract_flight_details(self, text: str) -> str:
        """Build a summary string with flight number and route.

        Args:
            text: Combined subject and body text.

        Returns:
            A human-readable flight detail string.
        """
        parts: list[str] = []
        fn_match = self.FLIGHT_NUMBER.search(text)
        if fn_match:
            parts.append(f"Flight {fn_match.group(1)}{fn_match.group(2)}")
        route_match = self.ROUTE_PATTERN.search(text)
        if route_match:
            parts.append(f"{route_match.group(1).upper()} → {route_match.group(2).upper()}")
        return " | ".join(parts) if parts else text[:120]

    def _extract_hotel_details(self, text: str, subject: str) -> str:
        """Extract property name from subject or body text.

        Args:
            text: Combined subject and body text.
            subject: The Subject header value.

        Returns:
            A human-readable hotel detail string.
        """
        property_patterns = [
            re.compile(r"(?:at|@)\s+(?:the\s+)?([A-Z][A-Za-z\s&']{2,40})", re.IGNORECASE),
            re.compile(
                r"(?:Hotel|Resort|Inn|Suites?)[:\s]+([A-Z][A-Za-z\s&']{2,40})", re.IGNORECASE
            ),
            re.compile(r"(?:Property|Accommodation)[:\s]+([A-Z][A-Za-z\s&']{2,40})", re.IGNORECASE),
        ]
        for pattern in property_patterns:
            match = pattern.search(subject)
            if match:
                return match.group(1).strip()
        for pattern in property_patterns:
            match = pattern.search(text)
            if match:
                return match.group(1).strip()
        return subject[:120] if subject else text[:120]

    def _dedup_trips(self, trips: list[TripSegment]) -> list[TripSegment]:
        """Deduplicate trip segments by confirmation number.

        Segments without a confirmation number are always kept. When multiple
        segments share the same confirmation number, only the first is retained.

        Args:
            trips: List of TripSegment instances to deduplicate.

        Returns:
            Deduplicated list preserving original order.
        """
        seen: set[str] = set()
        result: list[TripSegment] = []
        for segment in trips:
            if segment.confirmation_number is None:
                result.append(segment)
                continue
            if segment.confirmation_number not in seen:
                seen.add(segment.confirmation_number)
                result.append(segment)
        return result
