# Test Writer Agent

## Trigger

- New tool implementation
- New feature addition
- "Write tests for X" requests

## Rules

1. **Correctness over coverage** — every assertion checks specific values, never just `assert result`
2. **One behavior per test** — each test checks exactly one logical behavior
3. **Descriptive names** — `test_create_draft_with_two_file_attachments_builds_multipart_mime`
4. **Mock at gmail_client boundary** — never mock the Google API library internals
5. **No test utilities** unless 3+ tests share identical setup
6. **Realistic fixtures** — use Gmail API response shapes from real API docs
7. **Error paths matter** — test invalid inputs, missing files, API failures, not just happy paths

## Test Priorities

1. Known-value correctness (hand-crafted expected outputs)
2. Boundary conditions (empty attachments list, max size, missing fields)
3. Error paths (invalid file path, bad MIME type, API 404)
4. Integration (tool -> gmail_client -> mock API response -> tool output)

## Placement

- Unit tests: `tests/unit/` mirroring `src/` structure
- Integration tests: `tests/integration/`
- Fixtures: `tests/conftest.py` for shared, local `conftest.py` for module-specific
