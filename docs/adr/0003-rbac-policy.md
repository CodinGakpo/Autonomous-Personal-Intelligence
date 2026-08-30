# ADR-0003: Role-Based Access Control (RBAC) Policy

- **Status:** accepted
- **Date:** 2026-07-02

## Rule

### Role taxonomy

| Access role | Who holds it | Description |
|---|---|---|
| `admin` | Product owner, tech lead | Unrestricted. Can create auth accounts, onboard people, read all data. |
| `team_lead` | Team leads | Can onboard people and read all résumés/profiles. Cannot create auth accounts. |
| `developer` | All individual contributors | Can read and query own data only. |
| `hr` | HR / PM (Phase 2+) | Can onboard people and read all résumés/profiles. Cannot create auth accounts. |

`admin` is a strict superset of every other role. `team_lead` and `hr` share the same
privilege level but are separate roles so they can diverge in Phase 2.

### Access laws

1. **Résumés are private.** A `developer` may only access their own parsed résumé.
   `admin`, `team_lead`, and `hr` may access any résumé. (Law 1)

2. **Roster is partially redacted for developers.** A `developer` calling `GET /roster`
   receives all rows but with `email`, `clickup_task_id`, and `clickup_url` omitted for
   peers. Their own row is always returned in full. Privileged roles receive full rows.
   (Law 2)

3. **Onboarding is privileged.** `POST /onboarding` requires `admin`, `team_lead`, or
   `hr`. A `developer` receives 403. (Law 3)

4. **Auth account creation is admin-only.** `POST /auth/users` requires `admin`.
   (Law 4 — unchanged from pre-RBAC; now explicit.)

5. **Everything else (health, applications) is readable by all authenticated users.**
   (Law 5)

## Why

The system will grow to hold salary bands, promotion ratings, and performance composites
(§8.5 of the POC spec). This data is sensitive and drives pay/promotion decisions. Access
must be locked down now — before that data lands — so existing API contracts already
enforce the right boundaries. The cost of retrofitting RBAC after sensitive data is present
is significantly higher.

Résumés (Law 1) are the first piece of sensitive HR data in the system; the same laws will
extend naturally to performance scores and compensation data in Phase 1.

The roster redaction (Law 2) protects email addresses from being scraped by any team
member who happens to have a console account.

## Scope

`console/backend/rbac.py`, all `console/backend/` routes, and the
`tools/resume/` tool wrapper.

## Enforcement

- `console/backend/rbac.py` is the single source of truth for role sets and helpers
  (`require_role`, `assert_self_or_privileged`).
- All protected routes import from `rbac.py` — no inline `if user.role ==` checks outside
  that module.
- `console/backend/tests/test_rbac.py` has table-driven tests for every law.
- `import-linter` already guards that core packages do not import `console`; this ADR
  adds no new import rules.
