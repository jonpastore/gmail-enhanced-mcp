---
name: hud-refresh
description: Refresh HUD statusline with mail accounts, unread priority mail, and upcoming calendar events
---

Fetch current mail and calendar status and write it to the HUD data cache for statusline display.

## Steps

1. **Get mail accounts** — Call `gmail_list_accounts` to get the list of registered accounts.

2. **Get unread priority mail count** — Call `gmail_search_messages` with query `is:unread is:important` and `maxResults: 1` to get the unread important count from `resultSizeEstimate`. Do this for each account.

3. **Get upcoming calendar events** — Call `mcp__claude_ai_Google_Calendar__gcal_list_events` with:
   - `calendarId`: "primary"
   - `timeMin`: now (RFC3339 format, YYYY-MM-DDTHH:MM:SS)
   - `timeMax`: 24 hours from now
   - `timeZone`: "America/New_York"
   - `maxResults`: 5
   - `condenseEventDetails`: true

4. **Format the data** — Create a JSON object:
   ```json
   {
     "updated_at": "<ISO timestamp>",
     "accounts": [
       {"email": "jpastore79@gmail.com", "provider": "gmail", "unread_priority": 5},
       {"email": "jon@degenito.ai", "provider": "outlook", "unread_priority": 2}
     ],
     "calendar": [
       {"summary": "Standup", "start": "10:00 AM", "relative": "in 1h"},
       {"summary": "Design Review", "start": "2:00 PM", "relative": "in 5h"},
       {"summary": "1:1 with Vlad", "start": "9:00 AM tomorrow", "relative": "tomorrow"}
     ],
     "status_line": "mail:2acct unread:7 | cal:Standup(1h) Design(5h) 1:1(tmrw)"
   }
   ```

5. **Write to HUD cache** — Save the JSON to `.omc/state/mail-hud-data.json` using the Write tool.

6. **Display summary** — Show the status line and details:
   ```
   HUD refreshed:
     Mail: 2 accounts, 7 unread priority messages
     Calendar: 3 upcoming events
     Status: mail:2acct unread:7 | cal:Standup(1h) Design(5h) 1:1(tmrw)
   ```

## Notes
- The HUD shell script at `scripts/hud-mail-status.sh` reads `.omc/state/mail-hud-data.json` and outputs the `status_line` field
- Run this skill periodically or at session start to keep HUD data fresh
- Unread count uses `is:important` as a proxy for priority senders (Gmail's importance markers correlate with frequent contacts)
