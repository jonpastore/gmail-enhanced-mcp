# Testing Rules

## Framework

- pytest 8.x with pytest-cov
- All tests in `tests/` directory mirroring `src/` structure
- Shared fixtures in `tests/conftest.py`

## TDD Discipline

- Write the failing test FIRST
- Make it pass with minimal code
- Refactor while keeping tests green
- Never skip this cycle

## Test Organization

- `tests/unit/` — isolated tests with mocked dependencies
- `tests/integration/` — stdio roundtrip tests with mocked gmail_client
- Live tests marked with `@pytest.mark.live` — excluded by default

## Mocking Gmail API

- Mock at the `gmail_client.py` boundary, not the Google API library level
- Use `unittest.mock.patch` for gmail_client methods in tool tests
- Fixture `mock_gmail_client` in conftest.py provides a pre-configured mock
- Gmail API responses: use realistic JSON fixtures in `tests/fixtures/`

## Test Patterns

- One behavior per test function
- Test names describe the behavior: `test_create_draft_with_file_attachment_sets_mime_type`
- Use `pytest.raises` for expected exceptions, always check the message
- Float comparisons: `pytest.approx()` (not relevant here but convention)
- No `assert True` or `assert result is not None` without checking the value

## Fixtures

- `mock_gmail_client` — patched GmailClient with common responses
- `sample_message` — realistic Gmail message dict
- `sample_thread` — realistic thread with multiple messages
- `tmp_template_dir` — temporary directory for template tests
- `sample_attachment_bytes` — small PDF bytes for attachment tests

## Coverage

- Target: 90%+ for `src/`
- Exclude: `src/auth.py` live OAuth flow (interactive browser)
- Exclude: `src/main.py` entry point
- Fail build if coverage drops below threshold

## Markers

```python
@pytest.mark.live       # Requires real Gmail credentials
@pytest.mark.slow       # Takes >5 seconds
```

## Anti-Patterns

- Never test mock behavior — test that YOUR code handles the mock's return value correctly
- Never add test-only methods to production classes
- Never use `time.sleep()` in tests
- Never depend on test execution order
- Never share mutable state between tests
