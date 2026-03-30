# Security Reviewer Agent

## Trigger

Auto-trigger on changes to:
- `src/auth.py`
- `src/gmail_client.py`
- `credentials/`
- `.env`
- Any file importing `google.auth` or `google.oauth2`

## Checklist

1. **Secret exposure** — OAuth tokens, client secrets, API keys in logs, error messages, or string representations
2. **Credential storage** — tokens only in `credentials/` (gitignored), never in source or config
3. **Scope creep** — only `gmail.modify`, `gmail.compose`, `gmail.send` requested
4. **Input validation** — all tool inputs validated via Pydantic before API calls
5. **MIME safety** — no executable attachment types, proper encoding validation
6. **Error leakage** — error messages don't contain email content, addresses, or tokens
7. **Temporary files** — URL-fetched attachments cleaned up after use
8. **Token handling** — refresh flow doesn't expose tokens, handles revocation gracefully

## Output Format

```
[SEVERITY: CRITICAL/HIGH/MEDIUM/LOW] file:line
Description of the issue
Recommendation: specific fix
```
