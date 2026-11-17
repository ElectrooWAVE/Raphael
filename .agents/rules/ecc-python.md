# ECC Python & Common Rules

> **Precedence**: `.agents/rules/project-rules.md` wins on any conflict with this file.

## Coding Style & Design
- **Immutability**: Prefer creating new objects/DataFrames over mutating inputs in-place.
- **KISS / DRY / YAGNI**: Keep solutions simple; extract shared helpers only when repetition is real; avoid speculative abstractions.
- **File & Function Size**: Prefer small, focused modules (200–400 lines typical) and single-purpose functions (<50 lines) with shallow nesting and early returns.
- **Python Standards**: Follow PEP 8, use type annotations on function signatures, use `pathlib.Path`, context managers (`with`), `isinstance()` over `type() ==`, and `is None` over `== None`.
- **No Debug Leftovers**: Remove temporary `print()` / `console.log` debugging statements before committing. Avoid creating stray `.md` or `.txt` files.

## Error Handling & Validation
- Validate all external inputs at system boundaries (API payloads, query params, CSV/file inputs) with clear, fast-failing errors.
- Catch specific exceptions and chain with `raise ... from e`. Never silently swallow errors or return fake/fallback data.
- Never expose stack traces or internal secrets in client-facing error responses.

## Testing
- Use `pytest` with Arrange-Act-Assert structure and descriptive test names.
- Follow TDD (write test -> confirm failure -> minimal implementation -> refactor) where practical.
- Cover edge cases (`None`, `NaN`, zeros, boundary values, 400/404/500 error paths).
- Run `pytest -q` after every change; never report passing without running tests after the final edit.

## Security & Git Hygiene
- Never hardcode secrets, tokens, or credentials; use environment variables and `.gitignore`.
- Never use `innerHTML` for untrusted/error text; use `textContent` and parameterized queries.
- Use clear, scoped commit messages (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`) and review `git diff` before pushing.
