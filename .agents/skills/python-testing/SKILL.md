---
name: python-testing
description: Python testing strategies using pytest, TDD methodology, fixtures, mocking, parametrization, and coverage requirements. Use when writing pytest tests — fixtures, mocks, parametrization, or coverage.
metadata:
  origin: ECC
---

# Python Testing Patterns

Comprehensive testing strategies for Python applications using `pytest`, TDD methodology, and best practices.

## When to Activate

- Writing new Python code (follow TDD: red, green, refactor)
- Designing test suites for Python projects
- Reviewing Python test coverage
- Setting up testing infrastructure

## Core Testing Philosophy

1. **RED**: Write a failing test for the desired behavior.
2. **GREEN**: Write minimal code to make the test pass.
3. **REFACTOR**: Improve code while keeping tests green.

Target 80%+ code coverage and 100% on critical paths.

## pytest Fundamentals

- Use clear `assert` statements and `pytest.raises(ExcType, match=...)` for exceptions.
- Use `@pytest.fixture` (with `scope="module"` or `scope="session"` for expensive shared setup like datasets or models, and `tmp_path` for temporary files).
- Use `@pytest.mark.parametrize` with descriptive `ids=[...]` to test multiple inputs and edge cases.
- Use custom markers (e.g. `@pytest.mark.slow`, `@pytest.mark.integration`) registered in `pytest.ini` so fast unit tests can be run with `pytest -m "not slow"`.

## FastAPI Testing

- Use `httpx.AsyncClient` with `ASGITransport` (and `LifespanManager` if testing lifespan events) or `fastapi.testclient.TestClient` inside a `with TestClient(app) as client:` context manager so startup/shutdown lifespan handlers execute.

## Best Practices

### DO
- Follow Arrange-Act-Assert structure.
- Use descriptive test names (`test_unknown_series_returns_404`).
- Test edge cases: empty inputs, `None`/`NaN`, zeros, boundary values.
- Keep tests independent (no shared mutable state across tests).

### DON'T
- Don't test implementation details; test observable behavior.
- Don't ignore or skip failing tests or relax assertions.
- Don't catch exceptions manually in tests—use `pytest.raises`.
- Don't mock what the task requires testing with real execution.
