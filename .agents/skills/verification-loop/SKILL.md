---
name: verification-loop
description: Run a six-phase verification of your work — build, type check, lint, tests with coverage, security grep, and diff review — then produce a PASS/FAIL verification report. Use when verifying work after completing a feature or refactor, before creating a PR, or when quality gates must pass.
license: MIT
metadata:
  origin: ECC
---

# Verification Loop Skill

A comprehensive six-phase verification system before claiming work is complete.

## When to Use

- After completing a feature or significant code change
- Before creating a PR or committing
- When quality gates must pass
- After refactoring

## Verification Phases

1. **Build / Import Check**: Verify the application imports and starts cleanly without syntax or missing-dependency errors.
2. **Type Check**: Run the project's type checker if configured (e.g., `pyright .` or `mypy .`).
3. **Lint Check**: Run the project's linter if configured (e.g., `ruff check .`).
4. **Test Suite**: Run `pytest -q` (and `pytest --cov` if coverage is configured). Report exact counts of passed/failed tests.
5. **Security Scan**: Check changed files for hardcoded secrets (`sk-`, `api_key`, tokens, passwords) and leftover debug prints.
6. **Diff Review**: Run `git status` and `git diff --stat` to verify only intended files were modified, error handling is present, and edge cases are covered.

## Output Format

```text
VERIFICATION REPORT
==================
Build:     [PASS/FAIL]
Types:     [PASS/FAIL/N/A]
Lint:      [PASS/FAIL/N/A]
Tests:     [PASS/FAIL] (X passed, Y failed)
Security:  [PASS/FAIL]
Diff:      [X files changed]
```

Never claim tests or checks pass unless you ran them after your final edit and observed all reported cases pass.
