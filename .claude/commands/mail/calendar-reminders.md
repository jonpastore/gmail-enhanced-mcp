---
name: calendar-reminders
description: Ensure upcoming calendar events have 1-day and 1-hour reminders
---

Check all upcoming Google Calendar events for the next 7 days and ensure each has both a 1-day (1440 minute) and 1-hour (60 minute) popup reminder. Add missing reminders without duplicating existing ones.

## Steps

1. **List upcoming events** — Call `mcp__claude_ai_Google_Calendar__gcal_list_events` with:
   - `calendarId`: "primary"
   - `timeMin`: today's date at 00:00:00 (format: YYYY-MM-DDTHH:MM:SS)
   - `timeMax`: 7 days from now at 23:59:59
   - `timeZone`: "America/New_York"
   - `maxResults`: 50

2. **Check each event** — For each event returned, call `mcp__claude_ai_Google_Calendar__gcal_get_event` to get full details including current reminders.

3. **Evaluate reminders** — For each event:
   - Skip events where `myResponseStatus` is "declined"
   - Skip all-day events (they use different reminder logic)
   - Check if event has `reminders.useDefault: false` with custom overrides
   - Check if existing overrides include a popup reminder at 1440 minutes (1 day)
   - Check if existing overrides include a popup reminder at 60 minutes (1 hour)

4. **Add missing reminders** — For events missing either reminder, call `mcp__claude_ai_Google_Calendar__gcal_update_event` with:
   ```json
   {
     "calendarId": "primary",
     "eventId": "<event_id>",
     "event": {
       "reminders": {
         "useDefault": false,
         "overrides": [
           {"method": "popup", "minutes": 1440},
           {"method": "popup", "minutes": 60}
         ]
       }
     },
     "sendUpdates": "none"
   }
   ```
   When adding reminders, preserve any existing non-duplicate reminder overrides.

5. **Report summary** — Display:
   - Total events checked
   - Events skipped (declined or all-day)
   - Events already had both reminders
   - Events updated with missing reminders
   - List of updated event names

## Important
- Use `sendUpdates: "none"` to avoid notifying attendees about reminder changes
- Preserve existing reminders that aren't duplicates of the ones being added
- If an event uses default reminders (`useDefault: true`), switch to custom overrides with the two target reminders
