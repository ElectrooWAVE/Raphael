---
name: tdd-workflow
description: "Test-driven development workflow: write a failing test first, watch it fail, implement the smallest change to green, then refactor with 80%+ coverage across unit, integration, and E2E tests. Use when writing a new feature, fixing a bug, refactoring, or when told to write failing tests first."
metadata:
  origin: ECC
---

# Test-Driven Development Workflow

Ensures code development follows TDD principles with verifiable test coverage.

## When to Activate

- Writing new features or functionality
- Fixing bugs or issues
- Refactoring existing code
- Adding API endpoints

## Core Principles

1. **Tests BEFORE Code**: Write failing tests first (RED), implement the minimal change to pass (GREEN), then refactor while keeping tests green (REFACTOR).
2. **Coverage & Edge Cases**: Aim for 80%+ coverage across unit, integration, and E2E tests. Cover empty inputs, `None`/`NaN`, boundary conditions, and error paths.
3. **Test Isolation**: Each test sets up its own data and leaves no side effects.

## TDD Steps

1. **Identify User Journeys / Requirements**: Convert each requirement into a testable guarantee.
2. **Write Failing Tests (RED)**: Write tests using the project's runner (e.g., `pytest`) and run them to confirm they fail for the intended reason.
3. **Implement Minimal Code (GREEN)**: Write the smallest clean implementation needed to make the tests pass.
4. **Re-run Tests**: Confirm all tests pass without skipped or relaxed assertions.
5. **Refactor**: Remove duplication, improve naming, and keep functions small while keeping tests green.
6. **Verify**: Run the full test suite and report exact command output.
