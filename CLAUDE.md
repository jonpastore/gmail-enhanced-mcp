# Gmail Enhanced MCP — Project Contract

## Project Overview

Python MCP server providing full Gmail API access with attachment support for Claude Code.
Design spec: `docs/superpowers/specs/2026-03-30-gmail-enhanced-mcp-design.md`

## Build & Test Commands

```bash
# Run all tests
python -m pytest tests/ -v --tb=short

# Run unit tests only
python -m pytest tests/unit/ -v

# Run integration tests only
python -m pytest tests/integration/ -v

# Run with coverage
python -m pytest tests/ --cov=src --cov-report=term-missing --cov-fail-under=90

# Type check
python -m mypy src/ --strict

# Lint
python -m ruff check src/ tests/
python -m ruff format --check src/ tests/

# Format
python -m ruff format src/ tests/

# Auth setup
python -m gmail_mcp auth

# Start server (Claude Code launches this via package.json)
python -m gmail_mcp
```

## Tech Stack

- Python 3.11+
- Google Gmail API v1 via `google-api-python-client`
- OAuth2 via `google-auth-oauthlib`
- Pydantic 2.x for validation
- Loguru for logging
- JSON-RPC 2.0 over stdio

## Architecture Rules

- `gmail_client.py` is the ONLY file that touches the Gmail API
- Tools call `gmail_client` methods, never the API directly
- All tool functions return `dict` matching MCP content format
- Pydantic models validate all inputs at the tool boundary

## Code Quality Standards

- **File limit**: 500 lines max
- **Function limit**: 80 lines max
- **Cyclomatic complexity**: max 15 per function
- **Type hints**: Required on all public functions
- **Docstrings**: Required on all public functions (Google style)
- **Coverage**: 90%+ for src/

## ALWAYS Rules

1. ALWAYS write tests FIRST (TDD — red/green/refactor)
2. ALWAYS run `pytest` after editing any src/ file
3. ALWAYS run `mypy --strict` before considering a task complete
4. ALWAYS run `ruff check` and `ruff format --check` before commits
5. ALWAYS use Pydantic models for tool input validation
6. ALWAYS return actionable error messages (not raw API errors)

## NEVER Rules

1. NEVER send an email without explicit user approval
2. NEVER log email body content at any log level
3. NEVER log OAuth tokens or credentials
4. NEVER expose recipient lists in error messages
5. NEVER auto-retry a send operation on failure
6. NEVER store credentials outside `credentials/` directory
7. NEVER call Gmail API directly from tool functions (use gmail_client.py)
8. NEVER use `# type: ignore` without a comment explaining why
9. NEVER commit credentials, tokens, or .env files

## Verification Pipeline

1. `ruff format --check src/ tests/` — formatting
2. `ruff check src/ tests/` — linting
3. `mypy src/ --strict` — type checking
4. `pytest tests/unit/ -v` — unit tests
5. `pytest tests/integration/ -v` — integration tests
6. `pytest --cov=src --cov-fail-under=90` — coverage gate

## Docker Rules

- Use `docker compose` (not `docker-compose`)

## Active Skills

| Skill | Trigger |
|-------|---------|
| `superpowers:test-driven-development` | Any new feature or bugfix |
| `superpowers:verification-before-completion` | Before claiming work is done |
| `superpowers:systematic-debugging` | Any test failure or unexpected behavior |
| `superpowers:requesting-code-review` | Before merging |

## MCP Servers

| Server | Purpose |
|--------|---------|
| context7 | Google API documentation lookup |

## Subagents

| Agent | Triggers On |
|-------|------------|
| security-reviewer | Changes to `src/auth.py`, `src/gmail_client.py`, `credentials/` |
| test-writer | New tool implementation, new feature |

## Logging Standards

- Loguru with rotation (10MB, 3 backups)
- Log: tool call names, API response codes, auth events
- Never log: message bodies, attachments, email addresses, tokens
- Levels: DEBUG (dev only), INFO (normal ops), WARNING (degraded), ERROR (failures)
