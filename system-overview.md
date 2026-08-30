# Agent OS — System Overview (whole picture)

> Two views of the same system:
> **① PM view** — what it does, in plain English. **② Developer view** — components + data flow.
>
> Related: Plan B proposal (`docs/proposals/brain-architecture/plan-b-entity-graph/`, PR #43),
> POC design spec (`docs/superpowers/specs/2026-06-07-agent-os-poc-design.md`).

**One sentence:** Everything the company does flows into a shared **Brain**; the Brain then
answers questions (via the **Hermes** agent) and powers **dashboards** — every fact tagged with
where it came from and who's allowed to see it.

---

## ① PM view — what it does

```text
   WHO USES IT                          WHAT THEY GET
 ┌─────────────────┐      ┌────────────────────────────────────────┐
 │ 🧑 Team   (Slack)│ ───► │ "Turn this meeting into ClickUp tasks" │
 │ 👔 HR/Mgr (Web)  │ ───► │ Performance & weekly-review dashboards │
 │ 🧑‍💻 Staff  (Chat) │ ───► │ "What did I miss this week?"           │
 └─────────────────┘      └────────────────────────────────────────┘
                    │
                    ▼
        ╔═══════════════════════════════════════════════╗
        ║            🧠  THE COMPANY BRAIN               ║
        ║                                               ║
        ║  Remembers what happened, who did it, what    ║
        ║  was decided, and the skills people show —    ║
        ║  with the SOURCE of every fact and WHO may    ║
        ║  see it (comp/HR data stays private).         ║
        ╚═══════════════════════════════════════════════╝
                    ▲
                    │  keeps itself up to date from
                    │
   ┌────────────────────────────────────────────────────────┐
   │ ClickUp · Meeting recordings · Slack · Code · Résumés   │
   └────────────────────────────────────────────────────────┘
```

**Why it matters:** managers get trustworthy reports (every number is traceable), the team gets a
co-pilot that turns talk into tracked work, and sensitive data (pay, performance) is private by
design.

---

## ② Developer view — components & data flow

```text
 CLIENTS        💬 Slack                                 🌐 Browser
                   │                                        │
══SURFACES═════════╪════════════════════════════════════════╪═══════════════════
            ┌──────▼───────────────┐               ┌─────────▼──────────────┐
            │ HERMES AGENT     🟡  │               │ OPS CONSOLE (React) ✅ │
            │ Claude · skills · MCP│               │ dashboards · onboarding│
            └──────┬────────▲──────┘               └─────────┬──────────────┘
              ②query│  ⑤answer│                          ③read │ views
══BFF / API════════╪═════════╪═══════════════════════════════╪═════════════════
                   │         │                     ┌─────────▼──────────────┐
                   │         │                     │ OPS CONSOLE BFF     ✅ │
                   │         │                     │ FastAPI·auth·secrets   │
                   │         │                     └─────────┬──────────────┘
══BRAIN: READ══════╪═════════╪═══════════════════════════════╪═════════════════
            ┌──────▼─────────┴───────────────────────────────▼──────┐
            │ ACCESS CONTROL → PLANNER → (graph query + text search) │
            │ → fuse → cited answer (Hermes) / structured rows (UI)  │
            └───────────────────────────┬───────────────────────────┘
══BRAIN: STORE═════════════════════════╪═══════════════════════════════════════
            ┌───────────────────────────▼───────────────────────────┐
            │ ENTITY GRAPH  Person·Task·Decision·Meeting·Skill·PR…   │
            │ each fact: provenance · access class · history         │
            │ + materialized views (who's-doing-what, profiles)      │
            └───────────────────────────▲───────────────────────────┘
══BRAIN: WRITE═════════════════════════╪═══════════════════════════════════════
            ┌───────────────────────────┴───────────────────────────┐
            │ connectors → extractor(LLM) → resolver → upsert         │
            │              low confidence → review queue 👤           │
            └───────────────────────────▲───────────────────────────┘
══SOURCES══════════════════════════════╪═══════════════════════════════════════
        ClickUp ✅ · Fathom 🟡 · Slack · git · résumés · docs
              ▲ ①ingest only-what-changed         ④Hermes writes tasks back ┘
```

### Follow the numbers

| # | Flow | Path | LLM? |
|---|------|------|------|
| ① | **Ingest** | sources → write path → entity graph (keeps the Brain current) | yes (extractor) |
| ② → ⑤ | **Agent answer** | Slack → Hermes → Brain read → cited answer back to Slack | yes (Hermes) |
| ③ | **Dashboard** | browser → BFF → Brain views → chart/table | **no** — pure data |
| ④ | **Agent action** | Hermes creates a ClickUp task → re-enters via ① (closes the loop) | — |

### Where Hermes sits
Hermes is **not inside** the Brain — it's the **agent runtime beside it**, using the Brain as its
memory. It **reads** via MCP tools (`brain.query`, `brain.search`), **acts** by writing to ClickUp
(which loops back through ingest), and can optionally **be** the write-path extractor (swappable).
Chat surfaces go *through Hermes*; the dashboard reads Brain views *directly via the BFF*.

---

## Build status (today)

| Layer | Status |
|---|---|
| Ops Console: React UI + FastAPI BFF + Postgres | ✅ built |
| ClickUp client (`create_task`, `add_comment`) | ✅ built |
| Hermes deploy · MCP server · Fathom client · meeting→task skill | 🟡 stub / next |
| The Brain (entity graph, write path, views, access control) | ⬜ planned — Plan B (PR #43) |

Legend: ✅ built · 🟡 in progress · ⬜ planned · 👤 human-in-the-loop
