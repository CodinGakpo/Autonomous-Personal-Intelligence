# Agent OS — POC Design Spec

**Date:** 2026-06-07
**Owner:** Product
**Tech lead / DevOps:** Tech lead
**Status:** Approved for planning

---

## 1. Vision & North Star

**Agent OS is the second brain for the company** — a roster of role-based AI agents whose
job is **operational excellence**: run projects at velocity by templatizing everything,
keep people on-track and productive, and make performance visible. ClickUp is the single
source of truth; the agents synthesize existing information, maintain it, create new work
from it, and coach the team — improving over time through a behavioral loop.

**North-star metric:** team throughput per person at constant quality (velocity up without
rework up). "Throughput" is **not** raw task count — it is a composite the agent derives from
deep, per-person ClickUp activity:
- tasks assigned vs completed
- estimated vs actual hours logged
- comments and collaboration activity
- frequency and nature of changes to task fields/variables (status, estimates, etc.)
- working patterns over time (consistency, responsiveness, follow-through)

This composite powers three outcomes:
1. **Gamification** — the team sees how they're performing.
2. **A clear career path** — promotions, raises, and next compensation tied transparently to
   the metric.
3. **Skill intelligence** — mapping each person's core skills ("skill metrics") so we know
   exactly what talent is available for future projects.

Net framing: **project management and HR on steroids** — staff the right talent and deliver
the right project.

**Runtime:** [Hermes Agent](https://github.com/nousresearch/hermes-agent) (Nous Research,
MIT, v0.16.0) — self-improving skills, persistent memory, subagents, Slack gateway, MCP +
custom tools. We consume it as an upstream dependency (overlay repo, decision below).

---

## 2. Scope

This spec is implementation-plannable for **Phase 0 (the POC)** only. Later phases are
documented as roadmap context (Section 10) and each gets its own spec → plan → build cycle.

### In scope (Phase 0)
- **Track A — POC capability:** one Hermes instance = a user's co-pilot, wired to ClickUp +
  Fathom + Slack, proving one end-to-end loop.
- **Track B — Engineering harness:** the ADR / PRD / BDD / design-system specs plus the
  git-hook + CI enforcement loop that governs all code (human- and agent-written).

### Out of scope (roadmap)
Multi-instance role agents, CEO orchestrator, bootstrap/onboarding wizard, performance
dashboards, gamification, falling-behind detection, knowledge base generation, daily
check-ins, weekly workload/timesheet review automation, the performance + skill-intelligence
engine (Section 8.5), and the Google Workspace integrations (Section 6.1). (All in Section 10.)

---

## 3. Architecture

### Repo shape — Decision: (b) Overlay repo
This repository depends on Hermes upstream; it does **not** fork it. It contains only:
- `tools/` — custom Hermes tools we add (e.g. the Fathom tool)
- `clickup/` — the typed ClickUp client (built per the clickup-pack skills)
- `skills/` — Hermes skills (synthesis loop; agentskills.io-compatible)
- `docs/adr/`, `docs/prd/`, `features/`, `docs/design-system/` — the Track B harness
- `deploy/` — docker-compose for the Unraid server
- `.claude/` — **committed** team config: `settings.json` (shared skills/permissions so every
  developer and agent inherits the same harness). `.claude/settings.local.json` stays
  gitignored for per-developer overrides.
- CI config + git hooks

Rationale: Hermes is MIT and supports external tools / MCP / external skills, so we avoid
forking ~11k commits, keep the enforcement harness clean, and pull upstream updates (it
ships actively) without merge pain. Revisit only if we must modify Hermes core.

### Component boundaries (enforced by ADRs)
```
Slack (Hermes gateway)  ─┐
Fathom API ── tools/fathom ─┐
                            ├─► Hermes agent loop ──► skills/synthesis ──► clickup/ client ──► ClickUp API
ClickUp webhooks ───────────┘                                            (typed, layered)
```
- The Fathom tool MUST NOT write to ClickUp directly — it returns data the agent acts on.
- All ClickUp calls MUST go through the typed `clickup/` client, never raw HTTP.
- `tools/` MUST NOT import `gateway/` internals.

---

## 4. Track A — POC capability

**Deliverable:** one Hermes instance running on the Unraid server, reachable in Slack, that
performs this loop end-to-end:

> In Slack, a user points the co-pilot at a Fathom meeting → it synthesizes the minutes →
> creates a ClickUp task with the minutes recorded in it → confirms back in Slack.

Scope guardrails: one person, one ClickUp goal/list, one loop. No multi-instance,
no orchestration, no UI.

### Components
1. **Hermes runtime** — installed/configured; Slack gateway via `hermes gateway setup`;
   persistent memory + skills volumes mounted.
2. **Fathom tool** (`tools/fathom`) — authenticates to the Fathom API, fetches a meeting
   transcript by id/link, returns structured transcript text.
3. **ClickUp client** (`clickup/`) — typed wrapper for create-task + add-comment, built per
   `clickup-sdk-patterns` / `clickup-reference-architecture`.
4. **Synthesis skill** (`skills/meeting-to-task`) — Hermes skill that turns a transcript
   into structured minutes + a task payload. Implemented as a skill so it self-improves.

---

## 5. Track B — Engineering harness ("templatize everything")

The harness is the velocity engine: templates for code (ADR/PRD/BDD/design-system) and the
loop that enforces them. It comes online first/in parallel with Track A. **Owner: Tech lead.**

- **ADRs** — `docs/adr/NNN-title.md`: the rule, why it exists, which files/folders it
  governs. Enforced in Python by **import-linter** (module/import boundaries). On violation,
  the CI/hook error links the agent to the exact ADR so it reads the rationale and fixes it.
- **PRDs** — `docs/prd/*.md`, lightweight: **problem · goal · user journey**. Generated with
  `/write-prd`. Agents read the relevant PRD to ground context before writing code/tests.
- **BDD** — Gherkin `.feature` files in `features/`, run with Cucumber (`behave` for Python,
  `cucumber-js` for TS). Human-readable executable specs that link back to PRDs. Architectural
  rule: the **e2e suite is structurally forbidden from touching internals/DB** — it drives
  only through the real interface (Slack / CLI).
- **Design system** — `docs/design-system/` with component previews + rules (e.g. one primary
  button per view, no inline styles). Scoped to any web UI (Phase 2 dashboard). Inline-style
  linter wired now so it is ready when UI lands; not blocking Phase 0 (Slack/TUI only).
- **Enforcement loop** — **pre-commit git hooks** + **GitHub Actions CI** running the same
  checks so an agent that skips local hooks is caught on CI: formatter, type check
  (mypy/pyright + `tsc`), duplication (`jscpd`), **architecture check (import-linter vs
  ADRs)**, doc lint (markdownlint + ADR/PRD presence), and the BDD suite. A rejection links
  the agent to the failing ADR/BDD/PRD; it reads, fixes, retries.

---

## 6. ClickUp integration — mapped to the clickup-pack skills

Built using the installed `clickup-pack` skills rather than hand-rolled:

| Need | Skill |
|---|---|
| Token/OAuth + secrets | `clickup-install-auth`, `clickup-security-basics` |
| First calls / smoke test | `clickup-hello-world` |
| Tasks + comments CRUD | `clickup-core-workflow-a` |
| Spaces / lists / views | `clickup-core-workflow-b` |
| **Per-person Goals — weekly / monthly / quarterly** | `clickup-core-workflow-b` (Goals API) |
| **Project knowledge in ClickUp Docs** (per space/project) | `clickup-core-workflow-b` |
| Real-time triggers (agent reacts to ClickUp changes) | `clickup-webhooks-events` |
| Typed client, layered design | `clickup-sdk-patterns`, `clickup-reference-architecture` |
| Hardening | `clickup-rate-limits`, `clickup-prod-checklist`, `clickup-observability` |
| Pipeline (feeds Track B) | `clickup-ci-integration` |

Note: `clickup-deploy-integration` targets Vercel/Fly/Cloud-Run — we adapt its patterns to
docker-compose-on-Unraid, not follow it literally.

Per-person ClickUp **Goals are read at three cadences — weekly, monthly, quarterly** — and
become the agent's frame for synthesis, check-ins, and the performance composite.

---

## 6.1 Integration surface (full)

**Phase 0 (in scope):** Slack · Fathom · ClickUp (incl. ClickUp Docs + Goals).

**Roadmap integrations (Google Workspace + more):** we will mostly operate on a combination
of Google services plus ClickUp Docs. Added in Phase 1+:
- **Gmail** — read/triage email, draft + send on the agent's loop.
- **Google Calendar** — meeting awareness, scheduling, agenda placement.
- **Google Drive** — file context and storage.
- **Google Sheets** — structured data in/out (reporting, rosters, metrics exports).
- **Google Docs** — long-form docs the agent reads/writes.
- **ClickUp Docs** — the canonical project/space knowledge base for important information.

Each Google service is added via a Hermes tool (Google APIs / MCP); none are required for the
Phase 0 loop.

---

## 7. Deployment — Unraid

- **Target:** the company Unraid server (Docker).
- **Stack:** docker-compose (`deploy/`) — Hermes container + ClickUp client service; secrets
  via Unraid env / a secrets store; persistent volumes for Hermes memory + skills; Slack
  gateway.
- **Owner:** Tech lead (DevOps) — owns the stack, the enforcement harness, the ship-check gate,
  and the demo.

---

## 8. Operating cadence the system will support (Phase 1 target)

Documented here because it shapes the data model; automated in Phase 1, not Phase 0:
- **Weekly task estimation** — every task estimated week-to-week in ClickUp; the agent helps
  estimate and balance workload.
- **One weekly review meeting** — reviews **workload + timesheet** (estimated vs tracked
  time). The agent prepares the agenda and the review data.
- **Daily check-ins** — the agent DMs each team member daily in Slack to keep them on track.

---

## 8.5 Performance & Skill Intelligence (core pillar — roadmap)

This is the "HR on steroids" pillar. It is roadmap (Phase 1→2), but it shapes the Phase 0
data model, so it is captured here.

- **Performance composite** — per person, derived from the deep ClickUp activity in Section 1
  (assigned vs completed, estimated vs actual hours, comments/collaboration, field-change
  frequency/nature, working patterns over time). The agent computes and maintains it.
- **Gamification** — leaderboard + points dashboards in ClickUp so the team sees standings.
- **Compensation path** — promotions, raises, and next-compensation decisions tied
  transparently to the composite; a clear, legible path for each person.
- **Skill mapping ("skill metrics")** — the agent infers and maintains each person's core
  skills from their actual work, building a talent map of what's available for future
  projects. This is what lets PM + HR staff the right talent for the right project.

Sensitivity note: because this drives pay and promotion, the metric definition, transparency,
and a human-review gate are first-class design requirements when this pillar is specced.

---

## 9. Team & ownership

- **Product owner** — runs the PM skills, owns PRDs + OKRs.
- **Tech lead / DevOps** — runs the daily standup, owns Track B harness, Unraid
  deployment, ship-check gate, demo. Dogfoods the system with the team to test it.
- **Developers** — submit ADR-compliant PRs; the tech lead reviews and merges.
- **HR / PM / designers** — Phase 2+ users and feedback.

---

## 10. Roadmap (post-POC; each gets its own spec)

- **Phase 1** — harden the loop; estimated-vs-tracked-time synthesis; daily Slack check-ins;
  weekly workload + timesheet review prep; per-person Goal reads (weekly/monthly/quarterly);
  the **performance composite** (Section 8.5) + ClickUp performance dashboards; knowledge-base
  generation (auto-docs from transcripts + activity into ClickUp Docs); **Google Workspace
  integrations** (Gmail, Calendar, Drive, Sheets, Docs — Section 6.1); ClickUp fully
  dogfooded as source of truth.
- **Phase 2** — multi-instance role agents (HR, PM, dev-coach); CEO instance orchestrating
  via subagents and "hiring" new profiles; **gamification** (points/leaderboard); **skill
  mapping** + **compensation path** (Section 8.5, with human-review gate); falling-behind
  detection; first admin/metrics web UI (design system enforced here).
- **Phase 3** — human-in-the-loop bootstrap wizard; per-member profile agents at scale.

---

## 11. Success criteria (seed for /plan-okrs)

POC is successful when:
1. The co-pilot completes the Slack → Fathom → ClickUp loop unaided, producing a task whose
   recorded minutes are accurate enough to need no manual correction on a real meeting.
2. Track B rejects a deliberately ADR-violating PR locally (git hook) AND on CI.
3. The tech lead can stand the whole stack up on Unraid from `deploy/` and give the demo.

---

## 12. How the PM skills drive the build

`/write-prd` → `/red-team-prd` + `/pre-mortem` → `/plan-okrs` + `north-star` →
`/transform-roadmap` → `/write-stories` (backlog created **as ClickUp tasks** — dogfood day
one) → `/sprint` (Sprint 1 → tech lead + devs) → `/ship-check` + `/derive-tests` (demo gate).

---

## 13. Decisions made

- Hermes Agent is the runtime (not a custom framework).
- Overlay repo (b), not a fork.
- Deploy to Unraid via docker-compose.
- ClickUp built via the clickup-pack skills.
- `.claude/settings.json` is committed so the team shares one agent harness; `settings.local.json` is gitignored.
- Phase 0 held to one person / one loop + the Track B harness; everything else is roadmap.
