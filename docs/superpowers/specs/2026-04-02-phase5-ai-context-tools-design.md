# Phase 5 — AI Context Tools & Itinerary Aggregation

**Date:** 2026-04-02
**Status:** APPROVED
**Complexity:** MEDIUM
**Estimated new files:** 4 src + 4 test
**Estimated new LOC:** ~800 src + ~600 test

---

## Summary

Phase 5 adds 4 MCP tools (total becomes 38) that help Claude draft better email replies by providing structured thread context, identifying emails needing responses, batching draft creation, and extracting travel itineraries from email. The MCP server handles data extraction and Gmail/Outlook operations; Claude handles all reasoning and content generation.

All tools work with both Gmail and Outlook via the existing `EmailClient` ABC and `account` parameter routing.

---

## Design Principles

1. **MCP = data layer, not AI layer** — Tools extract structured context and handle mechanics. Claude provides intelligence.
2. **Multi-account by default** — All tools use the `account` parameter and `EmailClient` ABC. Gmail and Outlook work identically.
3. **Reuse existing infrastructure** — `DateParser` (Phase 4) for deadline extraction, `JunkDetector` (Phase 3) for filtering, `EmailClient` methods for all API access.
4. **No new dependencies** — Regex-based extraction, no NLP libraries.

---

## New MCP Tools (4 tools, total becomes 38)

### 1. `gmail_summarize_thread`

Read a thread and return structured context for Claude to reason over before drafting a reply.

```
Input: {
  threadId: string,
  account?: string
}

Output: {
  thread_id: string,
  message_count: int,
  participants: [{ email: string, name: string, message_count: int }],
  timeline: [{ from: string, date: string, snippet: string, has_attachments: bool }],
  key_asks: [string],
  deadlines: [string],
  open_questions: [string],
  attachments: [{ filename: string, message_id: string, attachment_id: string }]
}
```

**Implementation:**
- Calls `client.read_thread(threadId)` — works for both Gmail (threadId) and Outlook (conversationId)
- Parses From/To/CC headers from every message to build participant list
- Identifies "you" via `client.email_address`
- Timeline: chronological messages with from, date, first ~200 chars of body as snippet
- Key asks: scan bodies for action keywords (`please`, `could you`, `can you`, `need you to`, `action required`, `by [date]`)
- Deadlines: reuse `DateParser.extract_dates()` from Phase 4
- Open questions: lines containing `?` from messages NOT sent by you
- Attachments: aggregated from all messages in thread
- Body scanning capped at 10,000 chars per message to avoid token explosion

### 2. `gmail_needs_reply`

Find emails that likely need a response from you.

```
Input: {
  maxResults?: int (default 20),
  daysBack?: int (default 7),
  account?: string
}

Output: [{
  message_id: string,
  thread_id: string,
  from: string,
  subject: string,
  date: string,
  reason: string
}]
```

**Implementation:**
- Search: `is:inbox is:unread` (Gmail) / equivalent Outlook filter
- For each message, score against criteria (qualifies if 2+ match):
  1. You're in To: (not just CC)
  2. Last message in thread is NOT from you
  3. Message body contains a question mark
  4. Contains action-request keywords
  5. Not from a junk/noreply sender (reuse `JunkDetector.analyze()`)
  6. Received within `daysBack` window
- Returns sorted by date descending
- Each result includes `reason` field (e.g. "Direct question from alice@example.com, 2 days ago, no reply in thread")

### 3. `gmail_batch_reply`

Create drafts for multiple messages in one call.

```
Input: {
  replies: [{
    messageId: string,
    threadId: string,
    body: string,
    subject?: string
  }],
  account?: string
}

Output: {
  drafts_created: int,
  draft_ids: [string],
  errors: [string]
}
```

**Implementation:**
- Max 20 replies per call (hard limit, return error if exceeded)
- Loops through replies, calls `client.create_draft()` for each with `threadId` for proper threading
- Each draft created independently — one failure doesn't block others
- Returns both `draft_ids` (successes) and `errors` (failures)
- No sends — only drafts. User must explicitly send each one.

### 4. `gmail_extract_itinerary`

Scan emails for travel bookings, return structured timeline.

```
Input: {
  dateFrom?: string (default: today),
  dateTo?: string (default: 30 days ahead),
  maxResults?: int (default 50),
  account?: string
}

Output: {
  trips: [{
    type: "flight" | "hotel" | "car_rental" | "unknown",
    provider: string,
    confirmation_number: string | null,
    start_date: string,
    end_date: string | null,
    details: string,
    source_message_id: string
  }]
}
```

**Implementation:**
- Delegates to `ItineraryParser` in `src/itinerary_parser.py`
- Searches by booking-related keywords + provider-specific sender patterns
- Results sorted chronologically by `start_date`
- Deduplication by confirmation number
- Failed parsing → included as `type: "unknown"` with subject + message ID
- Date range validation: `dateFrom` must be before `dateTo`

---

## Architecture

### New files

| File | Purpose | Est. LOC |
|------|---------|----------|
| `src/tools/ai_context.py` | `gmail_summarize_thread` + `gmail_needs_reply` handlers | ~250 |
| `src/tools/batch_reply.py` | `gmail_batch_reply` handler | ~100 |
| `src/tools/itinerary.py` | `gmail_extract_itinerary` handler | ~150 |
| `src/itinerary_parser.py` | Booking extraction patterns + models | ~200 |

### Modified files

| File | Change |
|------|--------|
| `src/tools/__init__.py` | Register 4 new tools in `_HANDLER_MAP`, add tool definitions |

### Handler signatures

All 4 tools use the standard handler signature:
```python
def handle_*(args: dict[str, Any], client: EmailClient) -> dict[str, Any]
```

They go in `_HANDLER_MAP` (not triage or calendar maps) — no special dependencies needed.

### Key reuse

- `ImportanceScorer.extract_headers()` — header parsing in summarize_thread and needs_reply
- `DateParser.extract_dates()` — deadline extraction in summarize_thread
- `JunkDetector.analyze()` — filter junk senders in needs_reply
- `EmailClient` ABC — all tools work with Gmail and Outlook transparently

---

## Itinerary Parser Detail

### Booking types and detection

**Flights:**
- Search: `subject:(confirmation OR itinerary OR e-ticket OR boarding)` filtered by airline/OTA sender patterns
- Extract: airline, flight number (`[A-Z]{2}\d{2,4}`), route, date/time, PNR (`[A-Z0-9]{6}`), booking number (`Booking #\d+`)

**Hotels:**
- Search: `subject:(reservation OR confirmation OR booking)` filtered by hotel/OTA sender patterns
- Extract: property name, check-in/out dates, confirmation number, address

**Car rentals:**
- Search: `subject:(reservation OR confirmation)` filtered by rental company sender patterns
- Extract: company, pickup/dropoff dates and locations, confirmation number

### Sender pattern lists

Flights: `airline, airlines, airways, pacific, philippine, cebu, delta, united, american, southwest, jetblue, esky, expedia, orbitz, kayak`

Hotels: `hotel, resort, inn, marriott, hilton, hyatt, airbnb, agoda, orbitz, expedia, booking.com`

Car: `hertz, avis, enterprise, sixt, budget, national`

### Scope limits
- V1: English-language emails only
- Max 50 emails scanned per query (configurable via `maxResults`)
- Regex-based extraction, no NLP
- Graceful degradation: unparseable emails → `type: "unknown"`

---

## Error Handling & Guardrails

### Batch reply
- Max 20 replies per call — error if exceeded
- Independent draft creation — partial success returns both `draft_ids` and `errors`
- No sends, only drafts

### Itinerary parser
- Failed parsing → `type: "unknown"` with subject + message ID (no silent drops)
- Confirmation number dedup prevents duplicates from multiple emails
- Date range validation with sensible defaults

### Thread summarizer
- Body scanning capped at 10,000 chars per message
- Empty thread → error content
- Handles both Gmail thread format and Outlook conversationId transparently

### Privacy
- Never log email bodies, subjects, or addresses
- Itinerary confirmation numbers returned to Claude only, never logged
- Batch reply bodies provided by Claude — server doesn't generate or log content

---

## Task Flow (3 steps)

### Step 0: Itinerary parser + models
**Files:** `src/itinerary_parser.py`
- Pydantic models: `TripSegment`, `Itinerary`
- Sender pattern lists for flights, hotels, car rentals
- Regex patterns for confirmation numbers, dates, routes
- `ItineraryParser.parse_messages(messages) -> Itinerary`
- Deduplication by confirmation number

### Step 1: Tool handlers
**Files:** `src/tools/ai_context.py`, `src/tools/batch_reply.py`, `src/tools/itinerary.py`
- `handle_summarize_thread` — thread parsing, participant extraction, key asks/deadlines/questions
- `handle_needs_reply` — search + scoring criteria + reason generation
- `handle_batch_reply` — loop + create_draft + error collection
- `handle_extract_itinerary` — search + delegate to ItineraryParser

### Step 2: Registration + testing
**Files:** `src/tools/__init__.py`, all test files
- Register 4 tools in `_HANDLER_MAP` and `TOOL_DEFINITIONS`
- Unit tests for all handlers with mocked EmailClient
- Unit tests for ItineraryParser with realistic booking email fixtures
- Update tool count assertions (34 → 38)

---

## Success Criteria

1. `gmail_summarize_thread` returns structured context with participants, timeline, key asks, deadlines, and open questions for both Gmail and Outlook threads
2. `gmail_needs_reply` finds unread messages needing response, filters out junk, provides actionable reasons
3. `gmail_batch_reply` creates up to 20 drafts in one call, handles partial failures gracefully
4. `gmail_extract_itinerary` reconstructs the Philippines trip from Feb 2026 emails when given date range
5. All tools work with both Gmail (`jpastore79@gmail.com`) and Outlook (`jon@degenito.ai`) accounts
6. 418+ existing tests pass, ~40-50 new tests added
7. `mypy --strict`, `ruff check`, `ruff format --check` all pass
