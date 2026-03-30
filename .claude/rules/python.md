# Python Conventions

## Language Standards

- Python 3.11+ minimum
- Type hints on ALL public functions and methods (PEP 484/585)
- Use `from __future__ import annotations` for deferred evaluation
- Google-style docstrings on all public functions
- f-strings for string formatting (never `.format()` or `%`)

## Import Order (enforced by ruff)

1. Standard library
2. Third-party packages
3. Local imports

## Error Handling

- `raise` specific exceptions, never bare `Exception`
- Custom exceptions inherit from a project base: `GmailMCPError`
- Never use bare `except:` — always catch specific types
- Never `.unwrap()` equivalent: don't ignore return values from API calls

## Naming

- `snake_case` for functions, variables, modules
- `PascalCase` for classes and Pydantic models
- `UPPER_SNAKE_CASE` for constants
- Prefix private methods/attributes with `_`

## Patterns

- Pydantic v2 for all data validation (not dataclasses for external data)
- `pathlib.Path` for all file operations (not `os.path`)
- `typing.Optional[X]` written as `X | None` (Python 3.11+)
- Use `enum.StrEnum` for string enumerations
- Context managers for resource cleanup (`with` statements)

## Anti-Patterns

- No mutable default arguments
- No global state except module-level constants and the Config singleton
- No `*args, **kwargs` passthrough unless wrapping a well-typed interface
- No nested functions deeper than 2 levels
- No classes with only `__init__` and one method — use a function instead
