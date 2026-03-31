# Outlook API Reviewer Agent

## Trigger

Auto-trigger on changes to:
- `src/outlook_client.py`
- `src/outlook_query.py`

## Checklist

1. **Graph API call patterns** — All requests go through `_graph_get`/`_graph_post`/`_graph_patch`, never raw `requests` calls
2. **Rate limiting / throttling** — Check for 429 responses handled gracefully with retry guidance, not silent failures
3. **Response normalization** — Every method returns Gmail-compatible format (payload.headers, body.data, threadId = conversationId)
4. **Attachment size handling** — Files <3MB use inline `contentBytes`, >=3MB use upload sessions. Verify threshold is correct (3MB, not 4MB)
5. **Query translation fidelity** — `$search` and `$filter` are never combined in the same request (mutually exclusive). Folder operators (`in:inbox`) route to endpoint path changes, not filters
6. **Token handling** — Access tokens never logged, refresh handled transparently via MSAL cache
7. **Error messages** — Graph API errors mapped to actionable user messages (not raw 400/500 dumps)
8. **Pagination** — `@odata.nextLink` or `$skip`/`$top` handled correctly, `nextPageToken` normalized for tool consumers
9. **Permission scope** — Only `Mail.ReadWrite`, `Mail.Send`, `User.Read` used. No over-requesting scopes

## Output Format

```
[SEVERITY: CRITICAL/HIGH/MEDIUM/LOW] file:line
Description of the issue
Recommendation: specific fix
```
