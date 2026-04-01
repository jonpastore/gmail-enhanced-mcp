# Email Hygiene UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a single-page web UI for email triage, priority sender management, and newsletter cleanup, served from the existing MCP HTTP server.

**Architecture:** Three static files (`index.html`, `app.js`, `style.css`) in `src/ui/`, served via a new `/ui/*` Starlette route on the existing HTTP server (port 8420). The UI communicates with the backend via JSON-RPC `tools/call` requests using the same bearer token auth. Three new backend tools: `gmail_create_label`, `gmail_dismiss_contact`, `gmail_list_dismissed_contacts`.

**Tech Stack:** Vanilla HTML/CSS/JS (no framework, no build step), Starlette `StaticFiles`, existing MCP JSON-RPC protocol, SQLite triage cache.

**Spec:** `docs/superpowers/specs/2026-04-01-email-hygiene-ui-design.md`

---

### Task 1: Dismissed Contacts — Cache Layer

**Files:**
- Modify: `src/triage/cache.py`
- Test: `tests/unit/triage/test_cache.py`

- [ ] **Step 1: Write failing tests for dismissed contacts CRUD**

Add to `tests/unit/triage/test_cache.py`:

```python
class TestDismissedContacts:
    def test_dismiss_contact_stores_pattern(self, cache: TriageCache) -> None:
        cache.dismiss_contact("spam@example.com")
        dismissed = cache.get_dismissed_contacts()
        assert len(dismissed) == 1
        assert dismissed[0]["email_pattern"] == "spam@example.com"
        assert "dismissed_at" in dismissed[0]

    def test_dismiss_duplicate_is_idempotent(self, cache: TriageCache) -> None:
        cache.dismiss_contact("spam@example.com")
        cache.dismiss_contact("spam@example.com")
        dismissed = cache.get_dismissed_contacts()
        assert len(dismissed) == 1

    def test_is_dismissed_returns_true(self, cache: TriageCache) -> None:
        cache.dismiss_contact("spam@example.com")
        assert cache.is_dismissed("spam@example.com") is True

    def test_is_dismissed_returns_false(self, cache: TriageCache) -> None:
        assert cache.is_dismissed("good@example.com") is False

    def test_undismiss_contact(self, cache: TriageCache) -> None:
        cache.dismiss_contact("spam@example.com")
        cache.undismiss_contact("spam@example.com")
        assert cache.is_dismissed("spam@example.com") is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/triage/test_cache.py::TestDismissedContacts -v`
Expected: FAIL with `AttributeError`

- [ ] **Step 3: Add dismissed_contacts table to schema and implement methods**

In `src/triage/cache.py`, add to `_SCHEMA_SQL` after the `sync_state` table:

```sql
CREATE TABLE IF NOT EXISTS dismissed_contacts (
    email_pattern TEXT PRIMARY KEY,
    dismissed_at TEXT NOT NULL
);
```

Add these methods to the `TriageCache` class:

```python
    def dismiss_contact(self, email_pattern: str) -> None:
        """Add a contact pattern to the dismissed list."""
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO dismissed_contacts (email_pattern, dismissed_at) VALUES (?, ?)",
                (email_pattern, datetime.now(UTC).isoformat()),
            )
            self._conn.commit()

    def undismiss_contact(self, email_pattern: str) -> None:
        """Remove a contact pattern from the dismissed list."""
        with self._lock:
            self._conn.execute(
                "DELETE FROM dismissed_contacts WHERE email_pattern = ?",
                (email_pattern,),
            )
            self._conn.commit()

    def is_dismissed(self, email_pattern: str) -> bool:
        """Check if a contact pattern is dismissed."""
        row = self._conn.execute(
            "SELECT 1 FROM dismissed_contacts WHERE email_pattern = ?",
            (email_pattern,),
        ).fetchone()
        return row is not None

    def get_dismissed_contacts(self) -> list[dict[str, str]]:
        """List all dismissed contact patterns."""
        rows = self._conn.execute(
            "SELECT email_pattern, dismissed_at FROM dismissed_contacts ORDER BY dismissed_at DESC"
        ).fetchall()
        return [{"email_pattern": r[0], "dismissed_at": r[1]} for r in rows]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/triage/test_cache.py::TestDismissedContacts -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/triage/cache.py tests/unit/triage/test_cache.py
git commit -m "feat: add dismissed_contacts table to triage cache"
```

---

### Task 2: GmailClient — create_label

**Files:**
- Modify: `src/gmail_client.py`
- Test: `tests/unit/test_gmail_client.py`

- [ ] **Step 1: Write failing test**

Add to `tests/unit/test_gmail_client.py`:

```python
class TestCreateLabel:
    def test_creates_label_and_returns_id(self) -> None:
        mock_svc = MagicMock()
        mock_svc.users().labels().create().execute.return_value = {
            "id": "Label_99",
            "name": "My New Label",
        }
        client = _make_client(mock_svc)
        result = client.create_label("My New Label")
        assert result["id"] == "Label_99"
        assert result["name"] == "My New Label"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_gmail_client.py::TestCreateLabel -v`
Expected: FAIL

- [ ] **Step 3: Implement create_label**

Add to `src/gmail_client.py` after `extract_unsubscribe_link`:

```python
    def create_label(self, name: str) -> dict[str, Any]:
        """Create a new Gmail label.

        Args:
            name: Label name to create.

        Returns:
            Dict with id and name of the created label.
        """
        svc = self._get_service()
        label_body = {
            "name": name,
            "labelListVisibility": "labelShow",
            "messageListVisibility": "show",
        }
        result = svc.users().labels().create(userId="me", body=label_body).execute()
        logger.info(f"Created label: {result.get('name')} ({result.get('id')})")
        return {"id": result["id"], "name": result["name"]}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_gmail_client.py::TestCreateLabel -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/gmail_client.py tests/unit/test_gmail_client.py
git commit -m "feat: add create_label to GmailClient"
```

---

### Task 3: Tool Handlers — create_label, dismiss_contact, list_dismissed_contacts

**Files:**
- Modify: `src/tools/hygiene.py`
- Test: `tests/unit/tools/test_hygiene.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/unit/tools/test_hygiene.py`:

```python
from src.tools.hygiene import (
    handle_block_sender,
    handle_create_label,
    handle_dismiss_contact,
    handle_get_unsubscribe_link,
    handle_import_contacts_as_priority,
    handle_list_contacts,
    handle_list_dismissed_contacts,
    handle_report_spam,
    handle_trash_messages,
)


class TestHandleCreateLabel:
    def test_creates_label(self) -> None:
        client = _gmail_client()
        client.create_label.return_value = {"id": "Label_99", "name": "Test Label"}
        result = handle_create_label({"name": "Test Label"}, client)
        assert "Label_99" in result["content"][0]["text"]

    def test_requires_name(self) -> None:
        client = _gmail_client()
        result = handle_create_label({}, client)
        assert "name is required" in result["content"][0]["text"]

    def test_rejects_outlook(self) -> None:
        client = _outlook_client()
        result = handle_create_label({"name": "Test"}, client)
        assert "only available for Gmail" in result["content"][0]["text"]


class TestHandleDismissContact:
    def test_dismisses_contact(self, tmp_path: Any) -> None:
        client = _gmail_client()
        cache = TriageCache(tmp_path / "test.db")
        cache.initialize()
        result = handle_dismiss_contact({"pattern": "spam@test.com"}, client, cache)
        assert "Dismissed" in result["content"][0]["text"]
        assert cache.is_dismissed("spam@test.com")
        cache.close()

    def test_requires_pattern(self, tmp_path: Any) -> None:
        client = _gmail_client()
        cache = TriageCache(tmp_path / "test.db")
        cache.initialize()
        result = handle_dismiss_contact({}, client, cache)
        assert "pattern is required" in result["content"][0]["text"]
        cache.close()


class TestHandleListDismissedContacts:
    def test_lists_dismissed(self, tmp_path: Any) -> None:
        client = _gmail_client()
        cache = TriageCache(tmp_path / "test.db")
        cache.initialize()
        cache.dismiss_contact("spam@test.com")
        result = handle_list_dismissed_contacts({}, client, cache)
        assert "spam@test.com" in result["content"][0]["text"]
        cache.close()

    def test_empty_list(self, tmp_path: Any) -> None:
        client = _gmail_client()
        cache = TriageCache(tmp_path / "test.db")
        cache.initialize()
        result = handle_list_dismissed_contacts({}, client, cache)
        assert "No dismissed" in result["content"][0]["text"]
        cache.close()
```

Update the import at the top of the test file to include the new handlers.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/tools/test_hygiene.py::TestHandleCreateLabel tests/unit/tools/test_hygiene.py::TestHandleDismissContact tests/unit/tools/test_hygiene.py::TestHandleListDismissedContacts -v`
Expected: FAIL

- [ ] **Step 3: Implement handlers in src/tools/hygiene.py**

Add to `src/tools/hygiene.py`:

```python
def handle_create_label(args: dict[str, Any], client: EmailClient) -> dict[str, Any]:
    """Create a new Gmail label."""
    guard = _gmail_only(client)
    if guard:
        return guard

    name = args.get("name")
    if not name:
        return _text_content("name is required.")

    result = client.create_label(name)  # type: ignore[attr-defined]
    return _text_content(f"Created label: {result['name']} (ID: {result['id']})")


def handle_dismiss_contact(
    args: dict[str, Any], client: EmailClient, cache: TriageCache
) -> dict[str, Any]:
    """Dismiss a contact pattern from future resync."""
    guard = _gmail_only(client)
    if guard:
        return guard

    pattern = args.get("pattern")
    if not pattern:
        return _text_content("pattern is required.")

    cache.dismiss_contact(pattern)
    return _text_content(f"Dismissed {pattern}. It will not be re-added on resync.")


def handle_list_dismissed_contacts(
    args: dict[str, Any], client: EmailClient, cache: TriageCache
) -> dict[str, Any]:
    """List dismissed contact patterns."""
    guard = _gmail_only(client)
    if guard:
        return guard

    dismissed = cache.get_dismissed_contacts()
    if not dismissed:
        return _text_content("No dismissed contacts.")

    lines = [f"Dismissed contacts ({len(dismissed)}):"]
    for d in dismissed:
        lines.append(f"  {d['email_pattern']} (dismissed: {d['dismissed_at'][:10]})")
    return _text_content("\n".join(lines))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/tools/test_hygiene.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/tools/hygiene.py tests/unit/tools/test_hygiene.py
git commit -m "feat: add create_label, dismiss/list_dismissed_contacts handlers"
```

---

### Task 4: Register 3 New Tools

**Files:**
- Modify: `src/tools/__init__.py`
- Test: `tests/unit/test_tool_registry.py`

- [ ] **Step 1: Add imports**

In `src/tools/__init__.py`, update the hygiene import to include the new handlers:

```python
from .hygiene import (
    handle_block_sender,
    handle_create_label,
    handle_dismiss_contact,
    handle_get_unsubscribe_link,
    handle_import_contacts_as_priority,
    handle_list_contacts,
    handle_list_dismissed_contacts,
    handle_report_spam,
    handle_trash_messages,
)
```

- [ ] **Step 2: Add tool definitions**

Add to `TOOL_DEFINITIONS` list before the closing `]`:

```python
    {
        "name": "gmail_create_label",
        "description": "Create a new Gmail label.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Label name to create",
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "gmail_dismiss_contact",
        "description": "Dismiss a contact pattern so resync won't re-add it.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Email pattern to dismiss",
                },
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "gmail_list_dismissed_contacts",
        "description": "List all dismissed contact patterns.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
```

- [ ] **Step 3: Add handler map entries**

Add `handle_create_label` to `_HANDLER_MAP`:

```python
    "gmail_create_label": handle_create_label,
```

Add `handle_dismiss_contact` and `handle_list_dismissed_contacts` to `_TRIAGE_HANDLER_MAP` (they need TriageCache):

```python
    "gmail_dismiss_contact": handle_dismiss_contact,
    "gmail_list_dismissed_contacts": handle_list_dismissed_contacts,
```

- [ ] **Step 4: Update test assertions**

In `tests/unit/test_tool_registry.py`, update `test_all_28_tools_registered` to `test_all_31_tools_registered`:

Change the test name, add these to the `expected` set:
```python
            "gmail_create_label",
            "gmail_dismiss_contact",
            "gmail_list_dismissed_contacts",
```

Change the count assertion to `31`.

In `tests/integration/test_stdio_roundtrip.py`, change `28` to `31`.
In `tests/integration/test_triage_roundtrip.py`, change `28` to `31`.

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -v --tb=short`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/tools/__init__.py tests/unit/test_tool_registry.py tests/integration/test_stdio_roundtrip.py tests/integration/test_triage_roundtrip.py
git commit -m "feat: register 3 new tools (31 total: create_label, dismiss/list_dismissed)"
```

---

### Task 5: Static File Serving — HTTP Server

**Files:**
- Modify: `src/http_server.py`
- Create: `src/ui/` directory

- [ ] **Step 1: Create src/ui directory with a placeholder index.html**

Create `src/ui/index.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Gmail Enhanced — Email Hygiene</title>
    <link rel="stylesheet" href="style.css">
</head>
<body>
    <div id="app">Loading...</div>
    <script src="app.js"></script>
</body>
</html>
```

Create empty `src/ui/style.css` and `src/ui/app.js` placeholder files.

- [ ] **Step 2: Add static file mount to http_server.py**

In `src/http_server.py`, add import:

```python
from starlette.staticfiles import StaticFiles
```

In `create_app()`, add the `/ui` mount to the routes list:

```python
    ui_dir = Path(__file__).parent / "ui"

    return Starlette(
        routes=[
            Route("/health", health),
            Mount("/mcp", app=session_manager.handle_request),
            Mount("/ui", app=StaticFiles(directory=str(ui_dir), html=True), name="ui"),
        ],
        lifespan=lifespan,
        middleware=middleware,
    )
```

Add `from pathlib import Path` to the imports if not already present.

- [ ] **Step 3: Verify the server starts and serves the placeholder**

Run: `python -c "from src.http_server import create_app; from src.config import Config; app = create_app(Config()); print('App created with /ui route')"` 
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add src/http_server.py src/ui/
git commit -m "feat: add /ui static file serving to HTTP server"
```

---

### Task 6: Frontend — CSS Theme

**Files:**
- Create: `src/ui/style.css`

- [ ] **Step 1: Write the dark theme CSS**

Create `src/ui/style.css`:

```css
* { margin: 0; padding: 0; box-sizing: border-box; }

:root {
    --bg-primary: #1a1a2e;
    --bg-secondary: #16213e;
    --bg-panel: #0f3460;
    --text-primary: #eee;
    --text-secondary: #aaa;
    --text-muted: #666;
    --border: #333;
    --accent: #e94560;
    --accent-high: #f4a261;
    --accent-normal: #4ecca3;
    --accent-low: #666;
    --radius: 6px;
    --radius-sm: 4px;
    --radius-pill: 16px;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg-primary);
    color: var(--text-primary);
    font-size: 14px;
    line-height: 1.5;
    min-height: 100vh;
}

#app { max-width: 1200px; margin: 0 auto; padding: 0 16px; }

/* Auth screen */
.auth-screen {
    display: flex; flex-direction: column; align-items: center;
    justify-content: center; min-height: 80vh; gap: 16px;
}
.auth-screen input {
    padding: 10px 16px; width: 320px; background: var(--bg-secondary);
    border: 1px solid var(--border); border-radius: var(--radius);
    color: var(--text-primary); font-size: 14px;
}
.auth-screen button { padding: 10px 24px; }

/* Header & Tabs */
.header { padding: 16px 0; border-bottom: 1px solid var(--border); }
.header h1 { font-size: 18px; font-weight: 600; }
.tabs {
    display: flex; gap: 0; border-bottom: 1px solid var(--border);
    margin-top: 12px;
}
.tab {
    padding: 10px 20px; cursor: pointer; color: var(--text-muted);
    border-bottom: 2px solid transparent; font-size: 13px; font-weight: 500;
}
.tab.active { color: var(--accent); border-bottom-color: var(--accent); }
.tab:hover { color: var(--text-secondary); }

/* Account Switcher */
.account-bar {
    display: flex; gap: 8px; padding: 12px 0;
    border-bottom: 1px solid var(--border);
}
.account-btn {
    padding: 6px 14px; background: var(--bg-primary); border-radius: var(--radius);
    color: var(--text-muted); font-size: 13px; cursor: pointer;
    border: 1px solid var(--border);
}
.account-btn.active {
    background: var(--bg-panel); color: var(--accent);
    border-color: var(--accent);
}

/* Filter Chips */
.filter-bar {
    display: flex; gap: 8px; padding: 12px 0; flex-wrap: wrap;
    border-bottom: 1px solid var(--border); overflow-x: auto;
}
.chip {
    padding: 6px 12px; background: var(--border); border-radius: var(--radius-pill);
    color: var(--text-secondary); font-size: 12px; cursor: pointer;
    white-space: nowrap; border: 1px solid transparent;
}
.chip.active { background: var(--accent); color: white; }
.chip.alert { border-color: var(--accent); color: var(--accent); }
.chip .count { opacity: 0.7; margin-left: 4px; }

/* Sort Bar */
.sort-bar {
    display: flex; justify-content: space-between; align-items: center;
    padding: 8px 0; border-bottom: 1px solid #222; font-size: 12px;
    color: var(--text-muted);
}
.sort-bar label { display: flex; align-items: center; gap: 6px; }
.sort-options { display: flex; gap: 12px; }
.sort-options span { cursor: pointer; }
.sort-options span.active { color: var(--accent); }

/* Bulk Action Bar */
.bulk-bar {
    display: flex; gap: 8px; padding: 8px 12px; background: var(--bg-panel);
    border-bottom: 1px solid var(--border); align-items: center;
}
.bulk-bar .count { color: var(--accent); font-size: 12px; font-weight: 600; margin-right: 8px; }
.bulk-btn {
    padding: 4px 10px; background: var(--bg-primary); border-radius: var(--radius-sm);
    color: var(--text-secondary); font-size: 11px; cursor: pointer;
    border: 1px solid var(--border);
}
.bulk-btn:hover { border-color: var(--text-secondary); }
.bulk-btn.priority { color: var(--accent-normal); border-color: var(--accent-normal); }

/* Message Row */
.msg-row {
    display: flex; align-items: center; padding: 10px 4px;
    border-bottom: 1px solid #222; cursor: pointer;
}
.msg-row:hover { background: rgba(255,255,255,0.02); }
.msg-row.critical { background: rgba(233, 69, 96, 0.06); }
.msg-row.junk { opacity: 0.5; }
.msg-row input[type="checkbox"] { accent-color: var(--accent); margin-right: 12px; flex-shrink: 0; }

.priority-dot {
    width: 8px; height: 8px; border-radius: 50%; margin-right: 10px; flex-shrink: 0;
}
.priority-dot.critical { background: var(--accent); }
.priority-dot.high { background: var(--accent-high); }
.priority-dot.normal { background: var(--accent-normal); }
.priority-dot.low { background: var(--accent-low); }
.priority-dot.junk { background: var(--accent); opacity: 0.3; }

.msg-content { flex: 1; min-width: 0; }
.msg-header { display: flex; justify-content: space-between; margin-bottom: 2px; }
.msg-sender { font-weight: 600; }
.msg-sender.critical { color: var(--accent); }
.msg-sender.high { color: var(--accent-high); }
.msg-sender.normal { color: var(--accent-normal); }
.msg-email { color: var(--text-muted); font-weight: 400; font-size: 11px; margin-left: 4px; }
.msg-date { color: var(--text-muted); font-size: 11px; }
.msg-subject {
    color: var(--text-secondary); white-space: nowrap;
    overflow: hidden; text-overflow: ellipsis;
}
.msg-tags { display: flex; gap: 4px; margin-top: 4px; flex-wrap: wrap; }
.tag {
    padding: 1px 6px; background: var(--border); border-radius: 3px;
    font-size: 10px; color: var(--text-muted);
}
.tag.critical { background: var(--accent); color: white; }
.tag.high { background: var(--accent-high); color: var(--bg-primary); }
.tag.normal { background: var(--accent-normal); color: var(--bg-primary); }
.tag.junk { background: #442222; color: var(--accent); }
.tag.unsub { background: #222; color: var(--accent); cursor: pointer; }

.msg-actions {
    display: flex; gap: 6px; margin-left: 12px; flex-shrink: 0;
}
.action-btn {
    cursor: pointer; color: var(--text-muted); font-size: 14px;
    background: none; border: none; padding: 4px;
    border-radius: var(--radius-sm); min-width: 28px; min-height: 28px;
    display: flex; align-items: center; justify-content: center;
}
.action-btn:hover { background: rgba(255,255,255,0.1); color: var(--text-primary); }
.action-btn.star { color: var(--accent-normal); }

/* Pagination */
.pagination {
    display: flex; justify-content: center; gap: 12px;
    padding: 12px; color: var(--text-muted); font-size: 12px;
}
.pagination a { cursor: pointer; color: var(--accent); text-decoration: none; }
.pagination a.disabled { color: var(--text-muted); pointer-events: none; }

/* Priority Senders Tab */
.ps-section { margin: 16px 0; }
.ps-section h3 {
    font-size: 14px; color: var(--text-secondary); padding: 8px 0;
    border-bottom: 1px solid var(--border); margin-bottom: 8px;
}
.ps-row {
    display: flex; align-items: center; padding: 6px 0;
    border-bottom: 1px solid #222; font-size: 13px;
}
.ps-pattern { flex: 1; color: var(--text-primary); }
.ps-label { color: var(--text-secondary); margin-right: 12px; }
.ps-remove {
    color: var(--accent); cursor: pointer; font-size: 12px;
    background: none; border: none; padding: 4px 8px;
}
.ps-remove:hover { text-decoration: underline; }

/* Add Sender Form */
.add-form {
    display: flex; gap: 8px; padding: 12px 0;
    border-bottom: 1px solid var(--border); flex-wrap: wrap;
}
.add-form input, .add-form select {
    padding: 6px 10px; background: var(--bg-secondary);
    border: 1px solid var(--border); border-radius: var(--radius-sm);
    color: var(--text-primary); font-size: 13px;
}
.add-form input { flex: 1; min-width: 150px; }

/* Buttons */
button, .btn {
    padding: 6px 14px; background: var(--bg-panel); border: 1px solid var(--border);
    border-radius: var(--radius-sm); color: var(--text-primary);
    font-size: 13px; cursor: pointer;
}
button:hover, .btn:hover { border-color: var(--accent); }
button.primary { background: var(--accent); border-color: var(--accent); color: white; }

/* Newsletters Tab */
.nl-row {
    display: flex; align-items: center; padding: 10px 0;
    border-bottom: 1px solid #222; font-size: 13px;
}
.nl-row input[type="checkbox"] { accent-color: var(--accent); margin-right: 12px; }
.nl-info { flex: 1; }
.nl-sender { font-weight: 600; color: var(--text-primary); }
.nl-meta { color: var(--text-muted); font-size: 12px; margin-top: 2px; }
.nl-actions { display: flex; gap: 8px; }

/* Search bar */
.search-bar {
    padding: 8px 0; display: flex; gap: 8px;
}
.search-bar input {
    flex: 1; padding: 8px 12px; background: var(--bg-secondary);
    border: 1px solid var(--border); border-radius: var(--radius);
    color: var(--text-primary); font-size: 13px;
}

/* Label dropdown */
.label-dropdown {
    position: relative; display: inline-block;
}
.label-menu {
    position: absolute; top: 100%; right: 0; background: var(--bg-secondary);
    border: 1px solid var(--border); border-radius: var(--radius);
    min-width: 200px; z-index: 100; box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    max-height: 300px; overflow-y: auto;
}
.label-item {
    padding: 8px 12px; cursor: pointer; font-size: 13px;
    color: var(--text-secondary);
}
.label-item:hover { background: rgba(255,255,255,0.05); }
.label-item.create { color: var(--accent-normal); border-top: 1px solid var(--border); }

/* Loading / Empty */
.loading, .empty {
    display: flex; align-items: center; justify-content: center;
    min-height: 200px; color: var(--text-muted);
}

/* Responsive */
@media (max-width: 768px) {
    .msg-actions { display: none; }
    .msg-row { padding: 8px 0; }
    .filter-bar { flex-wrap: nowrap; overflow-x: auto; }
    .bulk-bar { flex-wrap: wrap; }
    .add-form { flex-direction: column; }
    .add-form input { min-width: unset; }
}

/* Touch targets */
@media (pointer: coarse) {
    .action-btn { min-width: 44px; min-height: 44px; }
    .chip { padding: 8px 14px; }
    .tab { padding: 12px 20px; }
}
```

- [ ] **Step 2: Commit**

```bash
git add src/ui/style.css
git commit -m "feat: add dark theme CSS for hygiene UI"
```

---

### Task 7: Frontend — HTML Shell

**Files:**
- Modify: `src/ui/index.html`

- [ ] **Step 1: Write the single-page HTML shell**

Replace `src/ui/index.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Gmail Enhanced — Email Hygiene</title>
    <link rel="stylesheet" href="style.css">
</head>
<body>
<div id="app">
    <!-- Auth Screen (shown if no token) -->
    <div id="auth-screen" class="auth-screen" style="display:none;">
        <h1>Gmail Enhanced MCP</h1>
        <p style="color:var(--text-muted);">Enter your MCP auth token</p>
        <input id="token-input" type="password" placeholder="MCP_AUTH_TOKEN">
        <button class="primary" onclick="App.authenticate()">Connect</button>
    </div>

    <!-- Main App (shown after auth) -->
    <div id="main" style="display:none;">
        <div class="header">
            <h1>Gmail Enhanced — Email Hygiene</h1>
            <div class="tabs">
                <div class="tab active" data-tab="inbox" onclick="App.switchTab('inbox')">Inbox Review</div>
                <div class="tab" data-tab="priority" onclick="App.switchTab('priority')">Priority Senders</div>
                <div class="tab" data-tab="newsletters" onclick="App.switchTab('newsletters')">Newsletters</div>
            </div>
        </div>

        <!-- Inbox Review Tab -->
        <div id="tab-inbox" class="tab-content">
            <div class="account-bar" id="account-bar"></div>
            <div class="filter-bar" id="filter-bar"></div>
            <div class="sort-bar">
                <label><input type="checkbox" id="select-all" onchange="Inbox.toggleSelectAll()"> Select all</label>
                <div class="sort-options">
                    <span class="active" onclick="Inbox.sort('score')">Priority Score</span>
                    <span onclick="Inbox.sort('date')">Date</span>
                    <span onclick="Inbox.sort('sender')">Sender</span>
                </div>
            </div>
            <div id="bulk-bar" class="bulk-bar" style="display:none;">
                <span class="count" id="selected-count">0 selected</span>
                <button class="bulk-btn" onclick="Inbox.bulkMoveTo()">Move to...</button>
                <button class="bulk-btn" onclick="Inbox.bulkTrash()">Trash</button>
                <button class="bulk-btn" onclick="Inbox.bulkSpam()">Spam</button>
                <button class="bulk-btn" onclick="Inbox.bulkBlock()">Block Senders</button>
                <button class="bulk-btn priority" onclick="Inbox.bulkPriority()">+ Priority</button>
            </div>
            <div id="message-list"></div>
            <div class="pagination" id="pagination"></div>
        </div>

        <!-- Priority Senders Tab -->
        <div id="tab-priority" class="tab-content" style="display:none;">
            <div class="add-form">
                <input id="ps-pattern" placeholder="Email or *@domain.com">
                <select id="ps-tier">
                    <option value="critical">Critical</option>
                    <option value="high">High</option>
                    <option value="normal" selected>Normal</option>
                </select>
                <input id="ps-label" placeholder="Label (e.g. Family)">
                <button class="primary" onclick="Priority.addSender()">Add</button>
            </div>
            <div style="display:flex; gap:8px; padding:12px 0;">
                <button onclick="Priority.importContacts()">Import Contacts</button>
                <button onclick="Priority.resyncContacts()">Resync Contacts</button>
            </div>
            <div class="search-bar">
                <input id="ps-search" placeholder="Search senders..." oninput="Priority.filter()">
            </div>
            <div id="priority-list"></div>
        </div>

        <!-- Newsletters Tab -->
        <div id="tab-newsletters" class="tab-content" style="display:none;">
            <div style="padding:12px 0; display:flex; gap:8px;">
                <button class="primary" onclick="Newsletters.scan()">Scan Inbox</button>
                <button onclick="Newsletters.bulkTrash()">Trash Selected</button>
                <button onclick="Newsletters.bulkBlock()">Block Selected</button>
            </div>
            <div id="newsletter-list"></div>
        </div>
    </div>

    <!-- Label Dropdown (reusable, positioned dynamically) -->
    <div id="label-dropdown" class="label-menu" style="display:none;"></div>
</div>
<script src="app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Commit**

```bash
git add src/ui/index.html
git commit -m "feat: add HTML shell for hygiene UI with 3 tabs"
```

---

### Task 8: Frontend — JavaScript Application

**Files:**
- Create: `src/ui/app.js`

- [ ] **Step 1: Write the MCP client and app controller**

Create `src/ui/app.js`:

```javascript
// MCP JSON-RPC client
const MCP = {
    token: null,
    baseUrl: '',

    init() {
        const params = new URLSearchParams(window.location.search);
        this.token = params.get('token') || localStorage.getItem('mcp_token');
        this.baseUrl = window.location.origin + '/mcp/';
    },

    async call(toolName, args = {}) {
        const resp = await fetch(this.baseUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${this.token}`,
            },
            body: JSON.stringify({
                jsonrpc: '2.0',
                method: 'tools/call',
                params: { name: toolName, arguments: args },
                id: Date.now(),
            }),
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        if (data.error) throw new Error(data.error.message);
        const text = data.result?.content?.[0]?.text || '';
        return text;
    },

    async listTools() {
        const resp = await fetch(this.baseUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${this.token}`,
            },
            body: JSON.stringify({
                jsonrpc: '2.0', method: 'tools/list', params: {}, id: Date.now(),
            }),
        });
        const data = await resp.json();
        return data.result?.tools || [];
    },
};

// App controller
const App = {
    currentTab: 'inbox',
    accounts: [],
    currentAccount: null,

    async init() {
        MCP.init();
        if (!MCP.token) {
            document.getElementById('auth-screen').style.display = '';
            return;
        }
        try {
            await MCP.listTools();
            localStorage.setItem('mcp_token', MCP.token);
            document.getElementById('auth-screen').style.display = 'none';
            document.getElementById('main').style.display = '';
            const acctText = await MCP.call('gmail_list_accounts');
            this.accounts = JSON.parse(acctText);
            this.currentAccount = this.accounts.find(a => a.default)?.email || this.accounts[0]?.email;
            this.renderAccounts();
            Inbox.load();
        } catch (e) {
            document.getElementById('auth-screen').style.display = '';
            console.error('Auth failed:', e);
        }
    },

    authenticate() {
        const token = document.getElementById('token-input').value.trim();
        if (!token) return;
        MCP.token = token;
        this.init();
    },

    switchTab(tab) {
        this.currentTab = tab;
        document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
        document.querySelectorAll('.tab-content').forEach(c => c.style.display = 'none');
        document.getElementById(`tab-${tab}`).style.display = '';
        if (tab === 'inbox') Inbox.load();
        else if (tab === 'priority') Priority.load();
        else if (tab === 'newsletters') Newsletters.load();
    },

    renderAccounts() {
        const bar = document.getElementById('account-bar');
        bar.innerHTML = this.accounts.map(a =>
            `<div class="account-btn ${a.email === this.currentAccount ? 'active' : ''}"
                  onclick="App.switchAccount('${a.email}')">${a.email}</div>`
        ).join('');
    },

    switchAccount(email) {
        this.currentAccount = email;
        this.renderAccounts();
        if (this.currentTab === 'inbox') Inbox.load();
    },
};

// Inbox controller
const Inbox = {
    messages: [],
    selected: new Set(),
    currentFilter: 'is:unread',
    currentSort: 'score',
    page: 0,
    pageToken: null,
    filters: [
        { id: 'attention', label: 'Needs Attention', query: 'is:unread is:important' },
        { id: 'unread', label: 'Unread', query: 'is:unread' },
        { id: 'people', label: 'People', query: 'is:unread category:primary' },
        { id: 'newsletters', label: 'Newsletters', query: 'has:nousersubs' },
        { id: 'promo', label: 'Promotional', query: 'category:promotions' },
        { id: 'unknown', label: 'Unknown Senders', query: 'is:unread -category:primary -category:social' },
    ],
    activeFilter: 'unread',

    async load() {
        const list = document.getElementById('message-list');
        list.innerHTML = '<div class="loading">Loading messages...</div>';
        this.selected.clear();
        this.updateBulkBar();
        this.renderFilters();

        try {
            const filter = this.filters.find(f => f.id === this.activeFilter);
            const query = filter ? filter.query : this.activeFilter;
            const args = { q: query, maxResults: 50 };
            if (App.currentAccount) args.account = App.currentAccount;
            if (this.pageToken) args.pageToken = this.pageToken;

            const text = await MCP.call('gmail_search_messages', args);
            const lines = text.split('\n');
            this.messages = [];
            let nextToken = null;

            for (const line of lines) {
                const idMatch = line.match(/id:\s*(\S+)\s+threadId:\s*(\S+)/);
                if (idMatch) {
                    this.messages.push({ id: idMatch[1], threadId: idMatch[2] });
                }
                const tokenMatch = line.match(/Next page token:\s*(\S+)/);
                if (tokenMatch) nextToken = tokenMatch[1];
            }
            this.pageToken = nextToken;
            this.renderMessages();
        } catch (e) {
            list.innerHTML = `<div class="empty">Error: ${e.message}</div>`;
        }
    },

    renderFilters() {
        const bar = document.getElementById('filter-bar');
        bar.innerHTML = this.filters.map(f =>
            `<div class="chip ${f.id === this.activeFilter ? 'active' : ''} ${f.id === 'unknown' ? 'alert' : ''}"
                  onclick="Inbox.setFilter('${f.id}')">${f.label}<span class="count"></span></div>`
        ).join('') + '<div class="chip" onclick="Inbox.customFilter()" style="border:1px dashed var(--border);">Custom...</div>';
    },

    setFilter(id) {
        this.activeFilter = id;
        this.pageToken = null;
        this.load();
    },

    customFilter() {
        const query = prompt('Enter Gmail search query:');
        if (query) {
            this.activeFilter = query;
            this.pageToken = null;
            this.load();
        }
    },

    async renderMessages() {
        const list = document.getElementById('message-list');
        if (!this.messages.length) {
            list.innerHTML = '<div class="empty">No messages found</div>';
            return;
        }

        let html = '';
        for (const msg of this.messages) {
            try {
                const args = { messageId: msg.id };
                if (App.currentAccount) args.account = App.currentAccount;
                const text = await MCP.call('gmail_read_message', args);
                const parsed = this.parseMessage(text, msg.id);
                html += this.renderRow(parsed);
            } catch (e) {
                html += `<div class="msg-row"><div class="msg-content">Error loading ${msg.id}</div></div>`;
            }
        }
        list.innerHTML = html;
        this.renderPagination();
    },

    parseMessage(text, id) {
        const lines = text.split('\n');
        const get = (prefix) => {
            const line = lines.find(l => l.startsWith(prefix));
            return line ? line.substring(prefix.length).trim() : '';
        };
        return {
            id,
            from: get('From:'),
            to: get('To:'),
            subject: get('Subject:'),
            date: get('Date:'),
            labels: get('Labels:'),
            threadId: get('Thread ID:'),
        };
    },

    renderRow(msg) {
        const sender = msg.from.split('<')[0].trim() || msg.from;
        const email = (msg.from.match(/<(.+)>/) || ['', msg.from])[1];
        const isUnread = msg.labels.includes('UNREAD');
        const checked = this.selected.has(msg.id) ? 'checked' : '';

        return `<div class="msg-row" data-id="${msg.id}">
            <input type="checkbox" ${checked} onchange="Inbox.toggleSelect('${msg.id}')">
            <div class="priority-dot normal"></div>
            <div class="msg-content" onclick="Inbox.preview('${msg.id}')">
                <div class="msg-header">
                    <span class="msg-sender">${sender}<span class="msg-email">${email}</span></span>
                    <span class="msg-date">${this.formatDate(msg.date)}</span>
                </div>
                <div class="msg-subject" style="${isUnread ? 'color:var(--text-primary);font-weight:600' : ''}">${msg.subject}</div>
            </div>
            <div class="msg-actions">
                <button class="action-btn" onclick="Inbox.trash(['${msg.id}'])" title="Trash">&#x1F5D1;</button>
                <button class="action-btn" onclick="Inbox.spam(['${msg.id}'])" title="Spam">&#x26D4;</button>
                <button class="action-btn" onclick="Inbox.blockSender('${email}')" title="Block">&#x1F6AB;</button>
            </div>
        </div>`;
    },

    formatDate(dateStr) {
        if (!dateStr) return '';
        try {
            const d = new Date(dateStr);
            const now = new Date();
            const diffMs = now - d;
            const diffH = Math.floor(diffMs / 3600000);
            if (diffH < 24) return `${diffH}h ago`;
            const diffD = Math.floor(diffH / 24);
            if (diffD < 7) return `${diffD}d ago`;
            return d.toLocaleDateString();
        } catch { return dateStr; }
    },

    toggleSelect(id) {
        if (this.selected.has(id)) this.selected.delete(id);
        else this.selected.add(id);
        this.updateBulkBar();
    },

    toggleSelectAll() {
        const all = document.getElementById('select-all').checked;
        this.messages.forEach(m => {
            if (all) this.selected.add(m.id); else this.selected.delete(m.id);
        });
        document.querySelectorAll('.msg-row input[type="checkbox"]').forEach(cb => cb.checked = all);
        this.updateBulkBar();
    },

    updateBulkBar() {
        const bar = document.getElementById('bulk-bar');
        const count = document.getElementById('selected-count');
        if (this.selected.size > 0) {
            bar.style.display = '';
            count.textContent = `${this.selected.size} selected`;
        } else {
            bar.style.display = 'none';
        }
    },

    async trash(ids) {
        if (!confirm(`Trash ${ids.length} message(s)?`)) return;
        const args = { messageIds: ids };
        if (App.currentAccount) args.account = App.currentAccount;
        await MCP.call('gmail_trash_messages', args);
        this.load();
    },

    async spam(ids) {
        if (!confirm(`Report ${ids.length} message(s) as spam?`)) return;
        const args = { messageIds: ids };
        if (App.currentAccount) args.account = App.currentAccount;
        await MCP.call('gmail_report_spam', args);
        this.load();
    },

    async blockSender(email) {
        if (!confirm(`Block all email from ${email}?`)) return;
        const args = { sender: email };
        if (App.currentAccount) args.account = App.currentAccount;
        await MCP.call('gmail_block_sender', args);
        this.load();
    },

    bulkTrash() { this.trash([...this.selected]); },
    bulkSpam() { this.spam([...this.selected]); },

    async bulkBlock() {
        const ids = [...this.selected];
        if (!confirm(`Block senders of ${ids.length} selected message(s)?`)) return;
        for (const id of ids) {
            const row = document.querySelector(`.msg-row[data-id="${id}"]`);
            const email = row?.querySelector('.msg-email')?.textContent;
            if (email) {
                const args = { sender: email };
                if (App.currentAccount) args.account = App.currentAccount;
                await MCP.call('gmail_block_sender', args);
            }
        }
        this.load();
    },

    async bulkPriority() {
        const tier = prompt('Priority tier (critical/high/normal):', 'normal');
        if (!tier) return;
        for (const id of [...this.selected]) {
            const row = document.querySelector(`.msg-row[data-id="${id}"]`);
            const email = row?.querySelector('.msg-email')?.textContent;
            const name = row?.querySelector('.msg-sender')?.childNodes[0]?.textContent?.trim();
            if (email) {
                await MCP.call('gmail_add_priority_sender', {
                    pattern: email, tier, label: name || email,
                });
            }
        }
        alert('Added to priority senders');
    },

    bulkMoveTo() {
        Labels.show(async (labelId) => {
            const args = { threadId: '', addLabelIds: [labelId], removeLabelIds: ['INBOX'] };
            for (const id of [...this.selected]) {
                const msg = this.messages.find(m => m.id === id);
                if (msg) {
                    args.threadId = msg.threadId;
                    if (App.currentAccount) args.account = App.currentAccount;
                    await MCP.call('gmail_modify_thread_labels', args);
                }
            }
            this.load();
        });
    },

    sort(by) {
        this.currentSort = by;
        document.querySelectorAll('.sort-options span').forEach(s => s.classList.remove('active'));
        event.target.classList.add('active');
        // Re-sort is handled server-side by different queries for now
    },

    preview(id) {
        // Could open a detail panel; for now just highlights the row
    },

    renderPagination() {
        const pag = document.getElementById('pagination');
        pag.innerHTML = `
            <span>Showing ${this.messages.length} messages</span>
            ${this.pageToken ? `<a onclick="Inbox.nextPage()">Next &rarr;</a>` : ''}
        `;
    },

    nextPage() { this.load(); },
};

// Labels helper
const Labels = {
    items: [],
    callback: null,

    async show(cb) {
        this.callback = cb;
        if (!this.items.length) {
            const text = await MCP.call('gmail_list_labels');
            try { this.items = JSON.parse(text); } catch { this.items = []; }
        }
        const dd = document.getElementById('label-dropdown');
        dd.innerHTML = this.items
            .filter(l => l.type === 'user')
            .map(l => `<div class="label-item" onclick="Labels.select('${l.id}')">${l.name}</div>`)
            .join('') +
            '<div class="label-item create" onclick="Labels.create()">+ Create new label</div>';
        dd.style.display = '';
        dd.style.position = 'fixed';
        dd.style.top = '50%';
        dd.style.left = '50%';
        dd.style.transform = 'translate(-50%, -50%)';
        document.addEventListener('keydown', Labels.dismiss, { once: true });
    },

    select(id) {
        document.getElementById('label-dropdown').style.display = 'none';
        if (this.callback) this.callback(id);
    },

    async create() {
        const name = prompt('New label name:');
        if (!name) return;
        const text = await MCP.call('gmail_create_label', { name });
        this.items = []; // force refresh
        Labels.show(this.callback);
    },

    dismiss(e) {
        if (e.key === 'Escape') document.getElementById('label-dropdown').style.display = 'none';
    },
};

// Priority Senders controller
const Priority = {
    senders: [],

    async load() {
        const list = document.getElementById('priority-list');
        list.innerHTML = '<div class="loading">Loading...</div>';
        try {
            const text = await MCP.call('gmail_list_priority_senders');
            this.senders = this.parseSenders(text);
            this.render();
        } catch (e) {
            list.innerHTML = `<div class="empty">Error: ${e.message}</div>`;
        }
    },

    parseSenders(text) {
        if (text.startsWith('No priority')) return [];
        const senders = [];
        let currentTier = '';
        for (const line of text.split('\n')) {
            const tierMatch = line.match(/^(CRITICAL|HIGH|NORMAL)/i);
            if (tierMatch) { currentTier = tierMatch[1].toLowerCase(); continue; }
            const entryMatch = line.match(/^\s+(.+?)\s+\((.+)\)$/);
            if (entryMatch) {
                senders.push({ pattern: entryMatch[1], label: entryMatch[2], tier: currentTier });
            }
        }
        return senders;
    },

    render() {
        const list = document.getElementById('priority-list');
        const search = (document.getElementById('ps-search')?.value || '').toLowerCase();
        const filtered = search
            ? this.senders.filter(s => s.pattern.toLowerCase().includes(search) || s.label.toLowerCase().includes(search))
            : this.senders;

        const grouped = { critical: [], high: [], normal: [] };
        filtered.forEach(s => (grouped[s.tier] || grouped.normal).push(s));

        let html = '';
        for (const [tier, senders] of Object.entries(grouped)) {
            if (!senders.length) continue;
            html += `<div class="ps-section"><h3>${tier.toUpperCase()} (${senders.length})</h3>`;
            for (const s of senders) {
                html += `<div class="ps-row">
                    <span class="ps-pattern">${s.pattern}</span>
                    <span class="ps-label">${s.label}</span>
                    <button class="ps-remove" onclick="Priority.remove('${s.pattern}')">Remove</button>
                </div>`;
            }
            html += '</div>';
        }
        list.innerHTML = html || '<div class="empty">No priority senders configured</div>';
    },

    filter() { this.render(); },

    async addSender() {
        const pattern = document.getElementById('ps-pattern').value.trim();
        const tier = document.getElementById('ps-tier').value;
        const label = document.getElementById('ps-label').value.trim();
        if (!pattern || !label) { alert('Pattern and label required'); return; }
        await MCP.call('gmail_add_priority_sender', { pattern, tier, label });
        document.getElementById('ps-pattern').value = '';
        document.getElementById('ps-label').value = '';
        this.load();
    },

    async remove(pattern) {
        if (!confirm(`Remove ${pattern}?`)) return;
        await MCP.call('gmail_remove_priority_sender', { pattern });
        await MCP.call('gmail_dismiss_contact', { pattern });
        this.load();
    },

    async importContacts() {
        if (!confirm('Import all Google contacts as normal-tier priority senders?')) return;
        const result = await MCP.call('gmail_import_contacts_as_priority', { tier: 'normal' });
        alert(result);
        this.load();
    },

    async resyncContacts() {
        if (!confirm('Re-sync contacts? Dismissed contacts will be skipped.')) return;
        const result = await MCP.call('gmail_import_contacts_as_priority', { tier: 'normal' });
        alert(result);
        this.load();
    },
};

// Newsletters controller
const Newsletters = {
    items: [],
    selected: new Set(),

    async load() {
        const list = document.getElementById('newsletter-list');
        list.innerHTML = '<div class="loading">Scanning for newsletters...</div>';
        try {
            await this.scan();
        } catch (e) {
            list.innerHTML = `<div class="empty">Error: ${e.message}</div>`;
        }
    },

    async scan() {
        const list = document.getElementById('newsletter-list');
        const args = { q: 'has:nousersubs', maxResults: 50 };
        if (App.currentAccount) args.account = App.currentAccount;
        const text = await MCP.call('gmail_search_messages', args);

        const lines = text.split('\n');
        const msgIds = [];
        for (const line of lines) {
            const m = line.match(/id:\s*(\S+)/);
            if (m) msgIds.push(m[1]);
        }

        // Group by sender
        const senderMap = {};
        for (const id of msgIds.slice(0, 30)) {
            try {
                const rArgs = { messageId: id };
                if (App.currentAccount) rArgs.account = App.currentAccount;
                const msgText = await MCP.call('gmail_read_message', rArgs);
                const fromLine = msgText.split('\n').find(l => l.startsWith('From:'));
                const from = fromLine ? fromLine.substring(5).trim() : 'Unknown';
                const email = (from.match(/<(.+)>/) || ['', from])[1];
                const name = from.split('<')[0].trim() || email;
                const key = email.toLowerCase();
                if (!senderMap[key]) senderMap[key] = { name, email, count: 0, lastId: id };
                senderMap[key].count++;
            } catch { /* skip */ }
        }

        this.items = Object.values(senderMap).sort((a, b) => b.count - a.count);
        this.render();
    },

    render() {
        const list = document.getElementById('newsletter-list');
        if (!this.items.length) {
            list.innerHTML = '<div class="empty">No newsletters detected</div>';
            return;
        }
        list.innerHTML = this.items.map(nl => `
            <div class="nl-row">
                <input type="checkbox" onchange="Newsletters.toggle('${nl.email}')">
                <div class="nl-info">
                    <div class="nl-sender">${nl.name}</div>
                    <div class="nl-meta">${nl.email} &middot; ${nl.count} emails</div>
                </div>
                <div class="nl-actions">
                    <button class="bulk-btn" onclick="Newsletters.unsubscribe('${nl.lastId}')">Unsubscribe</button>
                    <button class="bulk-btn" onclick="Newsletters.trashAll('${nl.email}')">Trash All</button>
                    <button class="bulk-btn" onclick="Newsletters.block('${nl.email}')">Block</button>
                </div>
            </div>
        `).join('');
    },

    toggle(email) {
        if (this.selected.has(email)) this.selected.delete(email);
        else this.selected.add(email);
    },

    async unsubscribe(msgId) {
        const args = { messageId: msgId };
        if (App.currentAccount) args.account = App.currentAccount;
        const result = await MCP.call('gmail_get_unsubscribe_link', args);
        const urlMatch = result.match(/URL:\s*(\S+)/);
        if (urlMatch) {
            window.open(urlMatch[1], '_blank');
        } else {
            alert(result);
        }
    },

    async trashAll(email) {
        if (!confirm(`Trash all emails from ${email}?`)) return;
        const args = { query: `from:${email}` };
        if (App.currentAccount) args.account = App.currentAccount;
        const result = await MCP.call('gmail_trash_messages', args);
        alert(result);
        this.scan();
    },

    async block(email) {
        if (!confirm(`Block ${email}?`)) return;
        const args = { sender: email };
        if (App.currentAccount) args.account = App.currentAccount;
        await MCP.call('gmail_block_sender', args);
        this.scan();
    },

    async bulkTrash() {
        for (const email of [...this.selected]) await this.trashAll(email);
    },

    async bulkBlock() {
        for (const email of [...this.selected]) await this.block(email);
    },
};

// Boot
document.addEventListener('DOMContentLoaded', () => App.init());
```

- [ ] **Step 2: Commit**

```bash
git add src/ui/app.js
git commit -m "feat: add JavaScript app for hygiene UI (MCP client, inbox, priority, newsletters)"
```

---

### Task 9: Add .superpowers to .gitignore

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Add .superpowers/ to .gitignore**

Append `.superpowers/` to `.gitignore`.

- [ ] **Step 2: Commit**

```bash
git add .gitignore
git commit -m "chore: add .superpowers/ to gitignore"
```

---

### Task 10: Full Verification

- [ ] **Step 1: Run full test suite**

Run: `pytest tests/ -v --tb=short`
Expected: All PASS with 31 tools registered

- [ ] **Step 2: Run linting and type checks**

Run: `ruff format --check src/ tests/ && ruff check src/ tests/`
Run: `mypy src/ --strict` (note: `src/ui/` is JS, not Python — mypy ignores it)

- [ ] **Step 3: Start server and test UI loads**

Run: `python -m gmail_mcp serve &`
Then: `curl -s http://localhost:8420/ui/ | head -5`
Expected: HTML content with `Gmail Enhanced — Email Hygiene` title

Run: `curl -s http://localhost:8420/health`
Expected: `{"status":"ok","version":"2.0.0"}`

- [ ] **Step 4: Kill test server**

Run: `kill %1`

- [ ] **Step 5: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix: verification fixes for hygiene UI"
```
