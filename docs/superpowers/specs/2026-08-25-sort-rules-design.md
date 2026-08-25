# Sort Rules — Design Spec

**Date:** 2026-08-25
**Status:** APPROVED (design); awaiting spec review
**Slice:** 1 of 4 (sort rules). Follow-ons: digest safety net, unsubscribe execute, attention.
**Complexity:** MEDIUM
**Providers:** Gmail and Outlook

---

## Summary

Add durable mail-sort rules that run **on the provider** (Gmail filters, Outlook inbox `messageRules`) so mail continues to file when this server is off. MCP tools create, list, and delete those rules after an explicit tool call. Matching mail **leaves Inbox** into a named folder. Creating a rule also files already-matching Inbox mail (capped).

This slice does **not** execute unsubscribe, change the digest, or auto-create rules from `JunkDetector`.

---

## Decisions (locked)

| ID | Decision |
|---|---|
| D1 | Hybrid: native provider rules do the sorting; MCP only proposes/creates/lists/deletes. |
| D2 | Starter folders plus custom destinations. Matching mail leaves Inbox. |
| D3 | Unified `MailRule` compiled to each provider. Provider is source of truth. No local rule database. |
| D4 | `Junk` is a **user** folder/label named `Junk`, not Gmail `SPAM` and not Outlook `junkemail`. `gmail_report_spam` / `gmail_block_sender` stay as they are (spam train / trash). |
| D5 | A tool call is the approval gate. No auto-create from triage. |
| D6 | Delete rule does not move mail back. Digest (slice 2) is the safety net for important unread mail already filed. |

---

## Scope

### In

- Starter folders on both providers: `Newsletters`, `Receipts`, `Finance`, `Travel`, `Social`, `Junk`
- Custom folder names on create
- Unified match: one `from` value (address **or** domain) and optional subject substring
- Action: skip Inbox (Gmail) or move (Outlook) into the destination
- Retroactive file of existing Inbox matches (default 200, hard max 500)
- List and delete native rules that skip Inbox / move to a folder
- OAuth scope adds so filter/rule **create** actually works
- Outlook `create_label` (create mail folder) and `move_messages`

### Out (later slices or never)

- Executing `List-Unsubscribe` / mailto unsubscribe
- Digest reading filed folders (slice 2; this spec only freezes folder names)
- Auto-sort from `JunkDetector` / `AutoSortProposal`
- Gmail raw query escape hatch
- SQLite rule store, disable/update rule, restore-on-delete
- Nested folders (`Receipts/Hotels`)
- UI changes
- Reporting as provider spam / trashing via these tools

### Non-goals that stay true

- Never send mail as part of sort
- Never log message bodies, subjects, or addresses
- Never call Gmail/Graph APIs from tool handlers (`gmail_client.py` / `outlook_client.py` only)
- Never auto-retry a failed move or rule create

---

## Users / outcomes

**User:** mailbox owner (Jon) operating through Claude / MCP on `jpastore79@gmail.com` and `jon@degenito.ai`.

**Outcomes:**

1. After one approved tool call, future mail from a sender or domain leaves Inbox into a chosen folder on that account, even if this server is down.
2. Existing Inbox matches are filed in the same call (up to the cap), with a count returned.
3. The same four tools work on Gmail and Outlook. Failures name the missing scope or provider limit, not a stack trace.

---

## Requirements

| ID | Statement | Priority | Acceptance |
|---|---|---|---|
| PRD-010 | `gmail_ensure_sort_folders` creates any missing starter folders on the selected account and is idempotent. | P0 | Second call creates zero folders; returns ids+names for all six. Extra names in `extra` are created the same way. |
| PRD-020 | `gmail_create_sort_rule` compiles a `MailRule` to a native Gmail filter or Outlook `messageRule`, enabled, that takes matching mail out of Inbox into `destination`. | P0 | After create, a newly arrived matching message is not in Inbox and is in the destination (provider-native; unit tests assert the request body). |
| PRD-030 | Create with `applyExisting=true` (default) files current Inbox matches, at most `maxExisting` (default 200, reject >500). | P0 | Returns `existing_moved`. Search is Inbox-only. No send. |
| PRD-040 | `gmail_list_sort_rules` returns provider rules that skip Inbox (Gmail `removeLabelIds` contains `INBOX`) or move to a folder (Outlook `moveToFolder` set). | P0 | Includes MCP-created rules. Gmail has no display name; `name` is synthesized `Sort: {from_value} → {destination}`. |
| PRD-050 | `gmail_delete_sort_rule` deletes by `ruleId`. Mail already filed is left in place. | P0 | Rule gone from list. Outlook `isReadOnly` → actionable error, not 500. |
| PRD-060 | Destination `Junk` is the user folder/label `Junk`, never system spam/trash. | P0 | Gmail action adds the user label id for `Junk`, not `SPAM`/`TRASH`. Outlook `moveToFolder` is the `Junk` mailFolder id, not `junkemail`. |
| PRD-070 | Tools work for `provider=gmail` and `provider=outlook`. No `_gmail_only` guard. | P0 | Outlook account on create_sort_rule does not return "only available for Gmail". |
| PRD-080 | Creating a rule whose destination folder is missing creates that folder first. | P0 | Custom destination `Vendors` appears in `list_labels` after create. |
| NFR-010 | Gmail filter **create** uses scope `gmail.settings.basic`. Add it to `SCOPES`. Missing scope error tells the user to re-auth. | P0 | `src/auth.py` includes the scope. 403 maps to "Missing OAuth scope(s): gmail.settings.basic. Run: python -m gmail_mcp auth". |
| NFR-020 | Outlook rule CRUD uses `MailboxSettings.ReadWrite`. Add to `MICROSOFT_SCOPES`. Azure app must grant the delegated permission. | P0 | Same error pattern. Folders/moves keep using `Mail.ReadWrite`. |
| NFR-030 | File ≤500 lines, function ≤80 lines, CC ≤15. `gmail_client.py` is already 523. New API calls still originate there; request bodies are built in `src/sort/` so the client stays thin wrappers. | P0 | Translators contain zero Google/Graph client calls. |
| NFR-040 | Retroactive moves: Gmail `messages.batchModify` (≤1000 ids/call); Outlook sequential `POST /me/messages/{id}/move`. No retries. Cap is the quota brake. | P0 | One failed move does not retry; remaining ids still attempted; return `existing_moved` + `existing_failed`. |
| DOM-010 | A `MailRule` has exactly one `from_value` (email containing `@`, or domain containing `.` and no `@`). Optional `subject_contains`. Destination is a non-empty folder name. | P0 | Invalid `from_value` rejected at Pydantic boundary before any API call. |
| DOM-020 | `STARTER_FOLDERS` is a public tuple imported by tools and, later, digest. | P0 | `("Newsletters", "Receipts", "Finance", "Travel", "Social", "Junk")` |
| DOM-030 | Gmail labels are tags; Outlook folders are locations. This product treats both as "leave Inbox into named destination." | P0 | Gmail: `addLabelIds=[dest], removeLabelIds=[INBOX]`. Outlook: `moveToFolder=folderId`. Outlook `modify_thread_labels` (categories) is **not** used to sort. |
| TRD-010 | Tool handlers call `EmailClient` methods only. | P0 | `src/tools/sort.py` does not import `googleapiclient` or call Graph URLs. |
| TRD-020 | `EmailClient` gains `@abstractmethod` `ensure_folders`, `list_sort_rules`, `create_sort_rule`, `delete_sort_rule`, `move_messages`. Outlook implements existing `create_label` as create-mail-folder. | P0 | Both subclasses implement all five. `gmail_create_label` MCP tool stays Gmail-guarded; Outlook folder create is used internally by `ensure_folders` / `create_sort_rule`. |
| TRD-030 | `create_block_filter` stays trash-on-from. It is not replaced. After `gmail.settings.basic` is added it should actually create. | P1 | Existing hygiene tests still pass. |

---

## Domain model

```python
STARTER_FOLDERS: tuple[str, ...] = (
    "Newsletters",
    "Receipts",
    "Finance",
    "Travel",
    "Social",
    "Junk",
)

class MailRuleMatch(BaseModel):
    from_value: str  # "news@example.com" or "example.com"
    subject_contains: str | None = None

class MailRule(BaseModel):
    id: str | None = None          # provider filter / messageRule id
    name: str                      # Outlook displayName; Gmail synthesized on list
    enabled: bool = True
    match: MailRuleMatch
    destination: str               # folder/label display name
    existing_moved: int = 0
    existing_failed: int = 0
```

`from_value` validation:

- Strip whitespace.
- If `@` in value: must be `local@domain` with a `.` in the domain. Stored lowercased.
- Else: domain only — at least one `.`, no spaces, no `*`. Stored lowercased.
- Anything else: validation error `"from_value must be an email address or a domain"`.

---

## Architecture

```
MCP tools (src/tools/sort.py)
        │  Pydantic at boundary
        ▼
EmailClient (ABC)
        │
        ├── GmailClient          OutlookClient
        │     │                       │
        │     │  bodies only          │  bodies only
        │     ▼                       ▼
        │  sort/gmail_translate    sort/outlook_translate
        ▼
Gmail settings.filters + labels     Graph mailFolders + messageRules
                                    Graph POST /me/messages/{id}/move
```

`src/sort/` contains no network I/O.

| File | Responsibility | Est. lines |
|---|---|---|
| `src/sort/__init__.py` | Export `STARTER_FOLDERS`, `MailRule`, `MailRuleMatch` | ~15 |
| `src/sort/models.py` | Pydantic models + `from_value` validator | ~80 |
| `src/sort/gmail_translate.py` | `MailRule` → Gmail filter JSON; Gmail filter JSON → `MailRule` | ~80 |
| `src/sort/outlook_translate.py` | `MailRule` + folder_id → Graph `messageRule` JSON; reverse | ~90 |
| `src/tools/sort.py` | Four handlers | ~160 |
| `src/gmail_client.py` | Thin wrappers that execute filters/labels/batchModify | +~80 wrappers |
| `src/outlook_client.py` | Folders, messageRules, move | +~120 |
| `src/email_client.py` | Abstract methods | +~40 |
| `src/auth.py` | Two scopes | +2 |
| `src/tools/__init__.py` | Register handlers | +8 |
| `src/tools/tool_schemas.py` | Four tool defs. File already exceeds 500 (schema dump; existing exemption). Append only. | +80 |

`gmail_client.py` is over the 500-line ceiling today. New logic that is **not** an API execute lives in `src/sort/`. Do not add a second Gmail API caller.

---

## Provider mapping

### Gmail filter body

```json
{
  "criteria": {
    "from": "<from_value>",
    "subject": "<subject_contains if set>"
  },
  "action": {
    "addLabelIds": ["<destination label id>"],
    "removeLabelIds": ["INBOX"]
  }
}
```

- `from` accepts both `user@domain` and `domain` (Gmail's filter `from` matches the domain suffix).
- Do not set `criteria.query` in v1.
- Ensure destination label exists (`list_labels` by `name`, else `create_label`).
- List: `users.settings.filters.list`. Keep entries whose `action.removeLabelIds` contains `INBOX`.
- Delete: `users.settings.filters.delete`.
- Retroactive: `messages.list` with `q='from:{from_value} in:inbox'` plus `subject:{subject}` when set, `maxResults=maxExisting`, then `messages.batchModify` add destination label, remove `INBOX`.
- Synthesized list name: `Sort: {from_value} → {destination}`. Resolve destination id → label name via `list_labels`. If the add-label is `TRASH` (block-sender filters), destination name is `TRASH` — those appear in the list; that is intended transparency, not a bug.

Gmail filters have no `displayName`. `MailRule.name` supplied on create is **not** stored on Gmail. Callers delete by `ruleId`.

### Outlook rule body

```json
{
  "displayName": "<name>",
  "sequence": <max(existing.sequence)+1 or 1>,
  "isEnabled": true,
  "conditions": {
    "fromAddresses": [{ "emailAddress": { "address": "<from_value>" } }]
  },
  "actions": {
    "moveToFolder": "<destination folder id>",
    "stopProcessingRules": false
  }
}
```

Domain match (no `@`): use `senderContains: ["<from_value>"]` instead of `fromAddresses`. `senderContains` is substring; `example.com` matches `news@example.com` and also `notexample.com` — documented limitation, accepted for v1. Do not invent a Graph query language.

Subject: add `subjectContains: ["<subject_contains>"]`.

- Folders: `GET /me/mailFolders`, match `displayName`; create with `POST /me/mailFolders` `{"displayName": name}`. Top-level only.
- `create_label(name)` on Outlook **creates a mail folder**, not a category. Sorting must move, not categorize.
- List rules: `GET /me/mailFolders/inbox/messageRules`. Keep those with `actions.moveToFolder`.
- Delete: `DELETE /me/mailFolders/inbox/messageRules/{id}`. If `isReadOnly`, return `"This Outlook rule is read-only and cannot be deleted via the API."`
- Sequence: do not preempt the user's existing rules. New rule `sequence = max(0, *sequences) + 1`.
- Retroactive: list Inbox messages matching from/subject (`$search` or `$filter` via existing `translate_gmail_query` / folder path `inbox`), cap `maxExisting`, `POST /me/messages/{id}/move` `{"destinationId": "<folder id>"}`.
- Deep folder listing: Graph `GET /me/mailFolders` is top-level. Starter folders are created top-level, so list is enough. `list_labels` may keep returning categories as `type=user` and folders as `type=system` (current behavior); `ensure_folders` matches **folder** `displayName` only.

---

## EmailClient methods

```python
def ensure_folders(self, names: list[str]) -> list[dict[str, str]]:
    """Create any missing folders/labels. Return [{id, name}, ...] for every name."""

def list_sort_rules(self) -> list[MailRule]:
    """Native skip-inbox / move-to-folder rules."""

def create_sort_rule(
    self,
    rule: MailRule,
    apply_existing: bool = True,
    max_existing: int = 200,
) -> MailRule:
    """Create native rule; optionally file existing Inbox matches."""

def delete_sort_rule(self, rule_id: str) -> None:
    """Delete native rule. Does not move mail."""

def move_messages(
    self,
    message_ids: list[str],
    destination_id: str,
) -> dict[str, Any]:
    """Take messages out of Inbox into destination. Return {moved: int, failed: int}."""
```

`create_sort_rule` algorithm (both providers):

1. Validate `max_existing` in `1..500` (tool layer also checks).
2. `ensure_folders([rule.destination])`; take id.
3. Translate + POST native rule; set `rule.id`.
4. If `apply_existing`: search Inbox matches, `move_messages`, set `existing_moved` / `existing_failed`. If `apply_existing` is false, skip search and ignore `max_existing`.
5. Return `MailRule`.

---

## MCP tools

Keep the `gmail_` prefix (existing convention). All four take optional `account`.

### `gmail_ensure_sort_folders`

```
Input: { extra?: string[], account?: string }
Output text: created vs already-existed per name, with ids.
```

Creates `STARTER_FOLDERS + extra`. Idempotent.

### `gmail_create_sort_rule`

```
Input: {
  name: string,                 # required
  fromValue: string,            # required
  destination: string,          # required
  subjectContains?: string,
  applyExisting?: bool,         # default true
  maxExisting?: int,            # default 200, max 500
  account?: string
}
```

Pydantic model at the handler (not raw dicts). Returns rule id, destination, `existing_moved`, `existing_failed`.

### `gmail_list_sort_rules`

```
Input: { account?: string }
Output text: one rule per line: id, name, from, destination, enabled.
```

### `gmail_delete_sort_rule`

```
Input: { ruleId: string, account?: string }
```

---

## OAuth / operator steps

**Gmail** — add to `SCOPES` in `src/auth.py`:

`https://www.googleapis.com/auth/gmail.settings.basic`

Then `python -m gmail_mcp auth` per Gmail account. Filter **create** is documented as this scope only; `gmail.modify` may list/get filters.

**Outlook** — add to `MICROSOFT_SCOPES`:

`https://graph.microsoft.com/MailboxSettings.ReadWrite`

Azure app registration (same app as Phase 2): add delegated **MailboxSettings.ReadWrite**, then re-auth `jon@degenito.ai`. Without the Azure permission, Graph returns 403 even after a local scope add.

Scope changes require re-authorization (existing project rule).

---

## Error handling

| Condition | Message (no addresses in unexpected errors; `fromValue` may appear on validation because the caller just supplied it) |
|---|---|
| Invalid `fromValue` | `from_value must be an email address or a domain` |
| `maxExisting` > 500 or < 1 | `maxExisting must be between 1 and 500` |
| Missing destination | `destination is required` |
| Gmail 403 on filters.create | `Missing OAuth scope(s): gmail.settings.basic. Run: python -m gmail_mcp auth` |
| Graph 403 on messageRules | `Missing OAuth scope(s): MailboxSettings.ReadWrite. Re-auth after adding the Azure delegated permission.` |
| Outlook read-only rule delete | `This Outlook rule is read-only and cannot be deleted via the API.` |
| Provider HTTP other | `Failed to create sort rule` / `Failed to list sort rules` / `Failed to delete sort rule` — no payload body, no recipient lists |

Do not log `from_value`, subjects, or message ids at INFO. DEBUG may log counts and rule ids.

---

## Testing

TDD. Mock at the client boundary for tool tests; mock Gmail service / Graph HTTP for client tests.

Required behaviors (one test each):

- `MailRuleMatch` accepts email and domain; rejects `*`, empty, `nodot`
- Gmail translator: from+destination → `from` criteria, add dest label, remove `INBOX`; never `SPAM`/`TRASH` for destination `Junk`
- Gmail translator reverse: skip-inbox filter → `MailRule`; non-skip-inbox filter omitted by list helper
- Outlook translator: email → `fromAddresses`; domain → `senderContains`; `moveToFolder` set; `stopProcessingRules` false
- `ensure_folders` creates missing, skips existing (both providers)
- `create_sort_rule` apply_existing true calls `move_messages` with Inbox hits only
- `create_sort_rule` apply_existing false does not search
- `max_existing` 501 rejected before API
- `delete_sort_rule` does not call move
- Outlook `create_label` POSTs `/me/mailFolders`
- Outlook `move_messages` POSTs `/me/messages/{id}/move`
- Tool handlers work with a mock Outlook client (`provider="outlook"`)
- Hygiene `gmail_block_sender` still targets TRASH
- Missing-scope errors are the strings above

No live tests required for merge. `@pytest.mark.live` optional later.

---

## Digest contract (slice 2, do not implement here)

Slice 2 will search these folder names for **unread** mail and score it, so important mail filed by native rules still appears in the daily digest. This slice freezes `STARTER_FOLDERS` and the leave-Inbox action so that search is possible. Do not change `DigestEngine` in this implementation.

---

## Success criteria

1. Four MCP tools registered and callable for Gmail and Outlook accounts.
2. Starter folders exist after `gmail_ensure_sort_folders` on both providers (mocked + live-optional).
3. Create rule produces a native skip-inbox / move rule; existing Inbox matches move up to the cap.
4. List shows those rules; delete removes the rule and leaves filed mail.
5. `Junk` destination is the user folder, not system spam/trash.
6. `gmail.settings.basic` and `MailboxSettings.ReadWrite` are in the auth scope lists.
7. Existing tests pass. New unit tests cover the table above.
8. `ruff` / `mypy --strict` clean on changed files.
9. `gmail_client.py` does not gain a second API module; sort translators have no network I/O.

---

## Change impact

| Artifact | Impact |
|---|---|
| Phase 1 "no action without user approval" | Tool call remains the approval. Creating a native rule is not a send. |
| Hygiene Gmail-only tools | Unchanged. Sort tools are the first hygiene-class tools that work on Outlook. |
| `AutoSortProposal` | Still proposals only. |
| Digest | Unchanged until slice 2. |
| OAuth | Re-auth both providers. Azure portal permission for Outlook. |
