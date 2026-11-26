# Security Policy

## Supported versions

| Version | Supported |
| --- | --- |
| `main` (latest release) | ✅ |
| feature branches | ❌ — not deployed |

## Reporting a vulnerability

Please **do not** open a public issue for a security problem.

1. Use GitHub's *Security → Report a vulnerability* (private advisory) on this
   repository, or
2. Contact the repository administrator directly through GitHub.

Include: affected component, reproduction steps, impact, and any suggested fix.
Expect an acknowledgement within a few days. This is an academic project, so
there is no bug-bounty programme.

## Secrets policy

- API keys, JWT secrets and database credentials live in `.env` only, which is
  git-ignored. `.env.example` documents the variables with placeholder values.
- Mobile builds must never embed Google/Weather/ML keys. All third-party calls
  are proxied by the backend.
- **If a secret is committed:** treat it as compromised. Revoke/rotate it at the
  provider first, then remove it from history. Deleting it in a later commit is
  not enough. Notify the repository administrator immediately.
- GitHub Actions uses repository secrets; workflows never echo secret values.

## Security measures implemented

- Passwords hashed with bcrypt (passlib), never logged.
- JWT access tokens (short-lived) plus refresh tokens; tokens are revocable
  server-side via a token-version claim.
- Pydantic schemas validate every request body/query; unknown fields rejected.
- SQLAlchemy ORM with bound parameters (no string-concatenated SQL).
- Per-user authorisation checks on every record endpoint (no IDOR: a user can
  only read/modify rows they own).
- CORS restricted to configured origins; security headers middleware.
- Rate limiting on authentication endpoints.
- `SECRET_KEY` placeholder is rejected at startup in production mode.
- Dependency and secret scanning run in CI where available.

## Known limitations

- TLS termination is the deployment's responsibility (use a reverse proxy).
- No MFA.
- Refresh-token theft detection is basic (rotation only).
