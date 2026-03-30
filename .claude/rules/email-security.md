# Email Security Rules

## Credential Handling

- OAuth tokens stored ONLY in `credentials/` (gitignored)
- `client_secret.json` NEVER committed to git
- Token refresh handled transparently — no token values in logs or errors
- If token file is corrupted, delete and re-auth (don't try to repair)

## OAuth Scopes

- Use minimum required scopes: `gmail.modify`, `gmail.compose`, `gmail.send`
- NEVER request `mail.google.com` (full unrestricted access)
- Scope changes require re-authorization

## API Safety

- Validate all inputs via Pydantic before making API calls
- Never construct Gmail API URLs via string concatenation
- Always use the Google API client library's built-in methods
- Rate limit awareness: return clear errors, never auto-retry sends

## MIME Construction

- Use Python's `email.mime` module (not manual string construction)
- Validate MIME types against known safe types
- Reject executable attachments: `.exe`, `.bat`, `.cmd`, `.scr`, `.js`, `.vbs`
- Validate base64 encoding before sending (catch corruption early)

## Data Handling

- Email content is PII — never log bodies, subjects, or addresses
- Attachment content is never logged
- Error messages must not leak email content
- Temporary files (URL downloads) cleaned up immediately after use

## Gmail API Quotas

- Default: 250 quota units/second per user
- messages.send = 100 units
- messages.get = 5 units
- messages.list = 5 units
- drafts.create = 10 units
- Don't batch aggressively — respect quotas
