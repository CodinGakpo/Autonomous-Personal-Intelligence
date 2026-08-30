# Employees page (frontend) — overview + backend payload

**Branch:** `hirak-console`  ·  **PR:** #40  ·  **Folder:** `console/frontend`

## What it is
A new **Employees** tab in the ops console: a roster list → click a person → their full
profile (avatar, résumé-style summary, skills) with an animated **track record** — tasks
assigned vs completed, completion %, and a weekly trend. Pure frontend, no new dependencies.

## What the backend needs to build
One endpoint:

```
GET /employees/{id}/profile      (id = the person's email)
```

Returns this **payload**:

```json
{
  "summary": "ML & frontend engineer. Built the dashboard and the Fathom webhook.",
  "skills": ["React", "TypeScript", "Python"],
  "assigned": 11,
  "done": 9,
  "weekly": [1, 2, 2, 1, 3, 3]
}
```

| Field | Type | Source |
|---|---|---|
| `summary` | string | generated from the person's uploaded **résumé** (2–3 sentences) |
| `skills` | string[] | extracted from the résumé |
| `assigned` | number | tasks assigned (**ClickUp**) |
| `done` | number | tasks completed (ClickUp) |
| `weekly` | number[] | tasks completed per recent week → trend chart |

## Notes
- The people **list** already uses the existing `GET /roster` — no change there.
- Per-person profile content is currently **mock data** in
  `console/frontend/src/data/profiles.ts` (the `EmployeeProfile` type). Replace that with a
  call to the endpoint above — nothing else in the UI changes.
