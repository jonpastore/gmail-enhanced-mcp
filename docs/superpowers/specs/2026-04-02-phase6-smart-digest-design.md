# Phase 6 — Smart Digest

**Date:** 2026-04-02
**Status:** APPROVED
**Complexity:** MEDIUM
**Estimated new files:** 5 src + 3 test + 1 script
**Estimated new LOC:** ~700 src + ~400 test

---

## Summary

Phase 6 adds a digest system that generates structured email summaries per account and optionally sends them as HTML emails with deep links back to each message. Two entry points: an MCP tool for on-demand use via Claude, and a standalone cron script for automated scheduling.

Each account gets its own digest sent to itself. Gmail digest → jpastore79@gmail.com, Outlook digest → jon@degenito.ai.

---

## Design Principles

1. **Orchestration, not intelligence** — DigestEngine assembles data from existing components (scorer, tracker, date parser, calendar). No LLM logic.
2. **Per-account isolation** — Each account's digest covers only that account's mail.
3. **Deep links** — Every item links directly to the message in Gmail/Outlook web UI.
4. **HTML email** — Digest sent as `text/html` with clickable links and light formatting.
5. **Cron-driven scheduling** — Same pattern as HUD refresh. No in-process scheduler.

---

## New MCP Tool (1 tool, total becomes 39)

### `gmail_generate_digest`

```
Input: {
  period?: "daily" | "weekly" (default: "daily"),
  sendEmail?: bool (default: false),
  maxResults?: int (default: 100),
  account?: string
}

Output: {
  account: string,
  period: string,
  generated_at: string,
  summary: {
    total_unread: int,
    by_category: {critical: int, high: int, normal: int, low: int, junk: int},
    top_items: [{message_id, from, subject, category, score, link}]
  },
  actionable: {
    needs_reply: [{message_id, from, subject, reason, link}],
    deadlines: [{message_id, subject, deadline_date, context, link}],
    overdue_followups: [{message_id, thread_id, sent_date, expected_days, link}],
    calendar_conflicts: [{email_message_id, date_mention, severity, link}]
  },
  sent: bool
}
```

- `sendEmail=false` by default — Claude must explicitly opt in
- Scores ALL fetched messages (up to maxResults), surfaces top 10
- Every item includes a `link` field with deep link to the message

---

## Architecture

### New files

| File | Purpose | Est. LOC |
|------|---------|----------|
| `src/digest/__init__.py` | Package exports | ~5 |
| `src/digest/engine.py` | DigestEngine — orchestrates data assembly | ~200 |
| `src/digest/formatter.py` | Format digest as HTML email with deep links | ~150 |
| `src/tools/digest.py` | `gmail_generate_digest` handler | ~80 |
| `scripts/generate-digest.py` | Standalone cron script | ~80 |

### Modified files

| File | Change |
|------|--------|
| `src/tools/__init__.py` | Register tool in _HANDLER_MAP |
| `src/tools/tool_schemas.py` | Add tool definition |
| `src/config.py` | Add digest config fields |

### Handler signature

Standard unified signature via HandlerContext:
```python
def handle_generate_digest(args: dict[str, Any], ctx: HandlerContext) -> dict[str, Any]
```

---

## DigestEngine

```python
class DigestResult(BaseModel):
    account: str
    period: str
    generated_at: str
    summary: DigestSummary
    actionable: DigestActionable
    sent: bool = False

class DigestSummary(BaseModel):
    total_unread: int
    by_category: dict[str, int]
    top_items: list[DigestItem]

class DigestItem(BaseModel):
    message_id: str
    from_addr: str
    subject: str
    category: str
    score: float
    link: str

class DigestActionable(BaseModel):
    needs_reply: list[dict[str, Any]]
    deadlines: list[dict[str, Any]]
    overdue_followups: list[dict[str, Any]]
    calendar_conflicts: list[dict[str, Any]]
```

`DigestEngine.generate()` orchestrates:
1. `client.search_messages(q="is:unread", max_results=N)` → unread messages
2. `ImportanceScorer(cache, calendar_ctx=...).score_messages(...)` → score ALL, categorize
3. Needs-reply logic (reuse from ai_context.py, extract as shared util)
4. `FollowUpTracker(cache).get_overdue(account)` → overdue followups
5. `DateParser().extract_dates(subject + snippet)` → deadlines from top items
6. If calendar_ctx: `calendar_ctx.get_today_events()` → calendar section
7. Generate deep links per provider

### Deep Links

```python
def _make_link(message_id: str, provider: str) -> str:
    if provider == "gmail":
        return f"https://mail.google.com/mail/u/0/#inbox/{message_id}"
    elif provider == "outlook":
        return f"https://outlook.live.com/mail/0/id/{message_id}"
    return ""
```

---

## HTML Formatter

Generates a clean HTML email body:

```html
<h2>Daily Digest — jpastore79@gmail.com</h2>
<p>April 3, 2026 8:00 AM ET | 47 unread</p>

<h3>Summary</h3>
<p>Critical: 2 | High: 5 | Normal: 28 | Low: 8 | Junk: 4</p>

<h3>Top Items</h3>
<ul>
  <li>[CRITICAL] <a href="https://mail.google.com/mail/u/0/#inbox/abc123">IRS Notice</a> — irs@irs.gov</li>
  <li>[HIGH] <a href="...">Re: Agoda Booking</a> — FLIGHTS_EN@agoda.com</li>
</ul>

<h3>Needs Your Reply (3)</h3>
<ul>
  <li><a href="...">Can you review the proposal?</a> — alice@example.com (2 days ago)</li>
</ul>

<h3>Follow-up Deadlines</h3>
<ul>
  <li><a href="...">Agoda claim</a> — deadline Apr 13</li>
</ul>

<h3>Overdue Follow-ups</h3>
<ul>
  <li><a href="...">PAL refund</a> — sent Mar 30, expected reply in 7d</li>
</ul>
```

Inline CSS for email client compatibility. No external stylesheets.

---

## Config

```python
self.digest_frequency: str = os.getenv("DIGEST_FREQUENCY", "daily")
self.digest_time: str = os.getenv("DIGEST_TIME", "08:00")
self.digest_day: str = os.getenv("DIGEST_DAY", "monday")  # for weekly
self.digest_timezone: str = os.getenv("DIGEST_TIMEZONE", self.user_timezone)
```

---

## Standalone Script

`scripts/generate-digest.py` — same pattern as `scripts/refresh-mail-hud.py`:
- Directly uses Google/MS APIs with existing tokens
- Accepts `--account` and `--period` flags
- Instantiates DigestEngine, generates, formats, sends
- Writes fallback to `.omc/state/last-digest-{account-hash}.json`
- Logs to stdout (cron redirects to `/tmp/digest.log`)

### Cron examples

Daily at 8am ET (both accounts):
```
0 8 * * * /path/to/python3 /path/to/scripts/generate-digest.py --account jpastore79@gmail.com
0 8 * * * /path/to/python3 /path/to/scripts/generate-digest.py --account jon@degenito.ai
```

Weekly Monday 8am:
```
0 8 * * 1 /path/to/python3 /path/to/scripts/generate-digest.py --account jpastore79@gmail.com --period weekly
```

---

## Error Handling & Guardrails

- Digest emails sent to account's own address only — never external
- Subject: `[Digest] Daily Email Summary — {date}` (filterable)
- `sendEmail=false` by default in MCP tool
- Calendar unavailable → omit calendar section, no error
- No unread → "All clear" digest, not silence
- One account fails → other account still generates (standalone script)
- Fallback: digest data written to `.omc/state/` even if send fails
- Score ALL fetched messages, surface top 10
- No body content in digest — subjects, senders, metadata only

---

## Success Criteria

1. `gmail_generate_digest` returns structured digest with summary + actionable items for both Gmail and Outlook
2. Every item includes a clickable deep link to the message
3. `sendEmail=true` sends an HTML email to the account's own address
4. Standalone script generates and sends digest independently of MCP server
5. Cron entries work for daily and weekly scheduling
6. No unread → "All clear" digest
7. Calendar section included when available, gracefully omitted when not
8. 477+ existing tests pass, ~30-40 new tests added
9. Lint and format clean
