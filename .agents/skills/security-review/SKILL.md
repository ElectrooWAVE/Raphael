---
name: security-review
description: Security review checklist and patterns for adding authentication, handling user input, managing secrets, creating API endpoints, or implementing sensitive features.
metadata:
  origin: ECC
---

# Security Review Skill

Ensures code follows security best practices and identifies potential vulnerabilities.

## When to Activate

- Handling user input or file uploads
- Creating new API endpoints
- Working with secrets, credentials, or environment variables
- Implementing authentication, authorization, or CORS

## Security Checklist

1. **Secrets Management**:
   - Never hardcode API keys, tokens, or passwords in source code.
   - Load secrets from environment variables; keep `.env` / `.env.local` in `.gitignore`.
2. **Input Validation**:
   - Validate all user/API inputs at system boundaries (e.g., Pydantic schemas in FastAPI, type/range checks).
   - Return clear 400/422 errors for invalid input without leaking stack traces.
3. **Injection & XSS Prevention**:
   - Use parameterized queries for SQL; never concatenate user input into queries or shell commands.
   - Escape or sanitize user-provided content before rendering in HTML (`textContent` over `innerHTML` for plain text/errors).
4. **Error Handling & Logging**:
   - Never expose stack traces, internal paths, or secrets in API error responses.
   - Log detailed errors server-side; return safe, actionable messages to clients.
5. **Dependencies & Static Files**:
   - Pin or bound dependencies cleanly; mount only intended static directories (never expose repo root or `.env`).
