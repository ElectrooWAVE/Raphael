---
name: python-patterns
description: Pythonic idioms, PEP 8 standards, type hints, and best practices for building robust, efficient, and maintainable Python applications. Use when writing or reviewing Python code and idiomatic structure, typing, or PEP 8 is in question.
metadata:
  origin: ECC
---

# Python Development Patterns

Idiomatic Python patterns and best practices for building robust, efficient, and maintainable applications.

## When to Activate

- Writing new Python code
- Reviewing Python code
- Refactoring existing Python code
- Designing Python packages/modules

## Core Principles

1. **Readability Counts**: Clear, obvious code over clever one-liners.
2. **Explicit is Better Than Implicit**: Avoid hidden side effects and magic.
3. **EAFP (Easier to Ask Forgiveness Than Permission)**: Prefer `try`/`except` with specific exceptions over LBYL checks where appropriate.

## Type Hints

Use modern Python 3.10+ type annotations on function signatures:

```python
def process_items(items: list[str]) -> dict[str, int]:
    return {item: len(item) for item in items}

def first(items: list[T]) -> T | None:
    """Return the first item or None if list is empty."""
    return items[0] if items else None
```

Use `Protocol` for structural duck typing and `@dataclass` / `NamedTuple` for structured data containers.

## Error Handling Patterns

- Catch **specific exceptions**; never use bare `except:` or silent `except Exception: return None`.
- Chain exceptions with `raise NewError(...) from e` to preserve tracebacks.
- Define a small custom exception hierarchy (e.g. `AppError`, `ValidationError`, `NotFoundError`) for domain errors.

## Context Managers & Generators

- Always use `with` for files, locks, connections, and transactions.
- Use generator expressions and `yield` functions for large datasets to avoid unnecessary intermediate lists.
- Join strings with `"".join(...)` rather than `+=` in loops.

## Anti-Patterns to Avoid

- Mutable default arguments (`def f(items=[])` -> use `items=None`).
- `type(obj) == list` -> use `isinstance(obj, list)`.
- `value == None` -> use `value is None`.
- `from module import *` -> use explicit imports.
- Bare `except:` -> catch specific exceptions and log or re-raise.
