# Implementation Agent Protocol

## Before Editing

1. **TARGET**: Identify the file(s) to edit/create
2. **READ FIRST**: Always read the current file before modifying
3. **CONVENTION CHECK**: Match existing patterns in the codebase

## Code Quality Policy (Strictly Enforced)

- Cyclomatic complexity: max 15 per function
- Function length: max 80 lines
- File length: max 500 lines (exemptions: test files)
- Type hints: required on all public interfaces
- No `# type: ignore` without explanation

## Validation Loop

After every change:

1. Run `ruff format --check` on changed files
2. Run `ruff check` on changed files
3. Run `mypy --strict` on changed files
4. Run `pytest` for affected test files
5. Check for: dead code, logic gaps, hardcoded values, insufficient tests, signature mismatches

Vary validation methods on every iteration. Only declare complete when multiple passes return clean.

## Output

After completing a task, provide:
- Files changed (with line counts)
- Tests added/modified
- Coverage impact
- Any deferred work noted
