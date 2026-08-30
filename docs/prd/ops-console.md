# PRD: Ops Console (v1)

## Problem

The team has no shared surface to bring a person into Agent OS or to see whether the system's
integrations (ClickUp, Slack, Fathom) are actually wired up. Onboarding and "is it connected?"
live in people's heads and scattered config, so the system is hard to adopt and hard to trust.

## Goal

A web app the team logs into to (1) **onboard a person** — name, role, Slack handle, and the
products they work on — recorded in ClickUp as the source of truth, and (2) see **integration
health** at a glance. Small but real full-stack, so later WBR / reporting / scoring screens
build on the same rails.

## User Journey

1. A team lead opens the console and signs in (email/password, v1).
2. The **Health** view shows ClickUp / Slack / Fathom as configured or not.
3. On **Onboard**, they enter a person's details, multi-select the products, and submit.
4. The backend writes the person to the ClickUp employees list (via `clickup/` client).
5. The person appears in the **Roster** with a link to their ClickUp record.
