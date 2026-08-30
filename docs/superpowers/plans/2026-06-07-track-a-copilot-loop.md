# Track A — Co-pilot Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the Phase-0 co-pilot loop: from Slack, point Hermes at a Fathom meeting → it fetches the transcript, synthesizes minutes, creates a ClickUp task with the minutes recorded, and confirms in Slack.

**Architecture:** An in-repo **MCP server** (`mcp_server/`) exposes three tools backed by typed clients — `fathom_get_transcript`, `clickup_create_task`, `clickup_add_comment`. Hermes connects to it via `~/.hermes/config.yaml`, so the tools appear as `mcp_agentos_*`. The synthesis logic is a Hermes **skill** (`SKILL.md`) so it self-improves. Slack is the Hermes gateway. Deploys on Unraid via docker-compose with a persistent volume for Hermes memory/skills/config.

**Tech Stack:** Python 3.11, `requests` (HTTP), `mcp` (FastMCP server), `responses` + `pytest` (tests), Hermes Agent (runtime), Docker Compose (Unraid).

**Depends on:** Plan 1 (Track B harness) merged — this plan fills the `tools/fathom`, `clickup/`, and `skills/` stubs and must pass every harness gate.

**Required secrets (env):** `FATHOM_API_KEY`, `CLICKUP_TOKEN`, `CLICKUP_LIST_ID` (target list for the POC), plus Slack app tokens (set during `hermes gateway setup`).

---

## File Structure

| Path | Responsibility |
|---|---|
| `pyproject.toml` | add runtime deps (`requests`, `mcp`) + dev deps (`responses`, `types-requests`); register `mcp_server` in import-linter |
| `tools/fathom/client.py` | implement `fetch_transcript` against the Fathom API (replaces Plan 1 stub) |
| `clickup/client.py` | implement `create_task` + `add_comment` against ClickUp v2 (replaces Plan 1 stub) |
| `mcp_server/__init__.py`, `mcp_server/server.py`, `mcp_server/__main__.py` | FastMCP server exposing the three tools |
| `skills/meeting-to-task/SKILL.md` | Hermes synthesis skill (the procedure) |
| `deploy/docker-compose.yml`, `deploy/.env.example`, `deploy/hermes-config.yaml` | Unraid deployment + MCP registration |
| `docs/adr/0002-external-apis.md` | ADR: external APIs only via typed clients; secrets only from env |
| `tests/test_fathom_client.py`, `tests/test_clickup_client.py`, `tests/test_mcp_server.py` | unit tests (HTTP mocked) |

---

## Task 1: Add dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add runtime + dev deps and register the MCP package**

In `pyproject.toml`, set `dependencies` and extend the dev group and import-linter root packages:

```toml
[project]
# ...existing fields...
dependencies = [
    "requests>=2.32",
    "mcp>=1.2",
]

[dependency-groups]
dev = [
    "ruff>=0.6",
    "mypy>=1.11",
    "import-linter>=2.0",
    "behave>=1.2.6",
    "pre-commit>=3.8",
    "pytest>=8.0",
    "responses>=0.25",
    "types-requests>=2.32",
]

[tool.importlinter]
root_packages = ["tools", "clickup", "skills", "mcp_server"]
```

- [ ] **Step 2: Sync and verify**

Run: `uv sync && uv run python -c "import requests, mcp, responses; print('deps ok')"`
Expected: prints `deps ok`.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add requests, mcp, and test deps for Track A"
```

---

## Task 2: Implement the Fathom client

**Files:**
- Modify: `tools/fathom/client.py`
- Test: `tests/test_fathom_client.py`

- [ ] **Step 1: Write the failing test** (`tests/test_fathom_client.py`)

```python
import responses

from tools.fathom.client import Transcript, fetch_transcript

URL = "https://api.fathom.ai/external/v1/recordings/123/transcript"


@responses.activate
def test_fetch_transcript_formats_segments(monkeypatch):
    monkeypatch.setenv("FATHOM_API_KEY", "test-key")
    responses.add(
        responses.GET,
        URL,
        json={
            "transcript": [
                {
                    "speaker": {"display_name": "Alice", "matched_calendar_invitee_email": "a@x.com"},
                    "text": "Let's ship the POC.",
                    "timestamp": "00:05:32",
                }
            ]
        },
        status=200,
    )

    result = fetch_transcript(123)

    assert isinstance(result, Transcript)
    assert result.recording_id == 123
    assert result.text == "00:05:32 Alice: Let's ship the POC."
    assert responses.calls[0].request.headers["X-Api-Key"] == "test-key"
```

- [ ] **Step 2: Run it to confirm failure**

Run: `uv run pytest tests/test_fathom_client.py -v`
Expected: FAIL (current `fetch_transcript` raises `NotImplementedError`; signature uses `meeting_id`).

- [ ] **Step 3: Implement the client** (replace the body of `tools/fathom/client.py`)

```python
"""Fathom tool. MUST NOT import clickup or write to ClickUp directly (ADR-0001).

It returns transcript data; the agent acts on it.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import requests

FATHOM_BASE = "https://api.fathom.ai/external/v1"
TIMEOUT_S = 30


@dataclass(frozen=True)
class Transcript:
    recording_id: int
    text: str


def fetch_transcript(recording_id: int) -> Transcript:
    """Fetch a Fathom meeting transcript and format it as 'HH:MM:SS Speaker: text' lines."""
    api_key = os.environ["FATHOM_API_KEY"]
    response = requests.get(
        f"{FATHOM_BASE}/recordings/{recording_id}/transcript",
        headers={"X-Api-Key": api_key},
        timeout=TIMEOUT_S,
    )
    response.raise_for_status()
    segments = response.json()["transcript"]
    lines = [
        f"{seg['timestamp']} {seg['speaker']['display_name']}: {seg['text']}"
        for seg in segments
    ]
    return Transcript(recording_id=recording_id, text="\n".join(lines))
```

- [ ] **Step 4: Run the test**

Run: `uv run pytest tests/test_fathom_client.py -v`
Expected: PASS.

- [ ] **Step 5: Type-check**

Run: `uv run mypy`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/fathom/client.py tests/test_fathom_client.py
git commit -m "feat: implement Fathom transcript client"
```

---

## Task 3: Implement ClickUp create_task

**Files:**
- Modify: `clickup/client.py`
- Test: `tests/test_clickup_client.py`

- [ ] **Step 1: Write the failing test** (`tests/test_clickup_client.py`)

```python
import responses

from clickup.client import ClickUpClient, TaskRef

CREATE_URL = "https://api.clickup.com/api/v2/list/900100/task"


@responses.activate
def test_create_task_returns_ref():
    responses.add(
        responses.POST,
        CREATE_URL,
        json={"id": "abc123", "url": "https://app.clickup.com/t/abc123"},
        status=200,
    )

    client = ClickUpClient(token="pk_test")
    ref = client.create_task("900100", "Meeting minutes — Jun 7", "## Minutes\n- ship POC")

    assert isinstance(ref, TaskRef)
    assert ref.id == "abc123"
    assert ref.url == "https://app.clickup.com/t/abc123"
    sent = responses.calls[0].request
    assert sent.headers["Authorization"] == "pk_test"
    assert b"markdown_description" in sent.body
```

- [ ] **Step 2: Run it to confirm failure**

Run: `uv run pytest tests/test_clickup_client.py::test_create_task_returns_ref -v`
Expected: FAIL (`NotImplementedError`).

- [ ] **Step 3: Implement the client** (replace the body of `clickup/client.py`)

```python
"""Typed ClickUp client. All ClickUp API access MUST go through this module (ADR-0001)."""
from __future__ import annotations

import os
from dataclasses import dataclass

import requests

CLICKUP_BASE = "https://api.clickup.com/api/v2"
TIMEOUT_S = 30


@dataclass(frozen=True)
class TaskRef:
    id: str
    url: str


class ClickUpClient:
    def __init__(self, token: str | None = None) -> None:
        self._token = token or os.environ["CLICKUP_TOKEN"]

    def _headers(self) -> dict[str, str]:
        return {"Authorization": self._token, "Content-Type": "application/json"}

    def create_task(self, list_id: str, name: str, description: str) -> TaskRef:
        response = requests.post(
            f"{CLICKUP_BASE}/list/{list_id}/task",
            headers=self._headers(),
            json={"name": name, "markdown_description": description},
            timeout=TIMEOUT_S,
        )
        response.raise_for_status()
        data = response.json()
        return TaskRef(id=data["id"], url=data["url"])

    def add_comment(self, task_id: str, text: str) -> None:
        raise NotImplementedError("Implemented in Task 4")
```

- [ ] **Step 4: Run the test + mypy**

Run: `uv run pytest tests/test_clickup_client.py -v && uv run mypy`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add clickup/client.py tests/test_clickup_client.py
git commit -m "feat: implement ClickUp create_task"
```

---

## Task 4: Implement ClickUp add_comment

**Files:**
- Modify: `clickup/client.py`
- Modify: `tests/test_clickup_client.py`

- [ ] **Step 1: Add the failing test** (append to `tests/test_clickup_client.py`)

```python
COMMENT_URL = "https://api.clickup.com/api/v2/task/abc123/comment"


@responses.activate
def test_add_comment_posts_text():
    responses.add(responses.POST, COMMENT_URL, json={"id": "c1"}, status=200)

    client = ClickUpClient(token="pk_test")
    client.add_comment("abc123", "Recorded from Fathom.")

    sent = responses.calls[0].request
    assert sent.headers["Authorization"] == "pk_test"
    assert b"comment_text" in sent.body
```

- [ ] **Step 2: Run it to confirm failure**

Run: `uv run pytest tests/test_clickup_client.py::test_add_comment_posts_text -v`
Expected: FAIL (`NotImplementedError`).

- [ ] **Step 3: Implement `add_comment`** (replace its body in `clickup/client.py`)

```python
    def add_comment(self, task_id: str, text: str) -> None:
        response = requests.post(
            f"{CLICKUP_BASE}/task/{task_id}/comment",
            headers=self._headers(),
            json={"comment_text": text},
            timeout=TIMEOUT_S,
        )
        response.raise_for_status()
```

- [ ] **Step 4: Run the tests + mypy**

Run: `uv run pytest tests/test_clickup_client.py -v && uv run mypy`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add clickup/client.py tests/test_clickup_client.py
git commit -m "feat: implement ClickUp add_comment"
```

---

## Task 5: Build the MCP server

**Files:**
- Create: `mcp_server/__init__.py`, `mcp_server/server.py`, `mcp_server/__main__.py`
- Test: `tests/test_mcp_server.py`

- [ ] **Step 1: Create `mcp_server/__init__.py`**

```python
"""Agent OS MCP server — exposes Fathom + ClickUp tools to Hermes."""
```

- [ ] **Step 2: Create the server** (`mcp_server/server.py`)

```python
"""FastMCP server. May use clickup + tools.fathom (ADR-0001 allows this direction)."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from clickup.client import ClickUpClient
from tools.fathom.client import fetch_transcript

mcp = FastMCP("agentos")


@mcp.tool()
def fathom_get_transcript(recording_id: int) -> str:
    """Return a Fathom meeting transcript as formatted text."""
    return fetch_transcript(recording_id).text


@mcp.tool()
def clickup_create_task(list_id: str, name: str, markdown_description: str) -> dict[str, str]:
    """Create a ClickUp task; returns its id and url."""
    ref = ClickUpClient().create_task(list_id, name, markdown_description)
    return {"id": ref.id, "url": ref.url}


@mcp.tool()
def clickup_add_comment(task_id: str, text: str) -> str:
    """Add a comment to a ClickUp task."""
    ClickUpClient().add_comment(task_id, text)
    return "ok"
```

- [ ] **Step 3: Create the entrypoint** (`mcp_server/__main__.py`)

```python
from mcp_server.server import mcp

if __name__ == "__main__":
    mcp.run()
```

- [ ] **Step 4: Write the test** (`tests/test_mcp_server.py`)

```python
import responses

from mcp_server import server


@responses.activate
def test_fathom_tool_wraps_client(monkeypatch):
    monkeypatch.setenv("FATHOM_API_KEY", "k")
    responses.add(
        responses.GET,
        "https://api.fathom.ai/external/v1/recordings/7/transcript",
        json={
            "transcript": [
                {"speaker": {"display_name": "Bob", "matched_calendar_invitee_email": None},
                 "text": "Hi", "timestamp": "00:00:01"}
            ]
        },
        status=200,
    )
    assert server.fathom_get_transcript(7) == "00:00:01 Bob: Hi"


@responses.activate
def test_clickup_create_tool_wraps_client(monkeypatch):
    monkeypatch.setenv("CLICKUP_TOKEN", "pk")
    responses.add(
        responses.POST,
        "https://api.clickup.com/api/v2/list/55/task",
        json={"id": "t1", "url": "u"},
        status=200,
    )
    assert server.clickup_create_task("55", "n", "d") == {"id": "t1", "url": "u"}
```

- [ ] **Step 5: Run the tests + mypy + architecture check**

Run: `uv run pytest tests/test_mcp_server.py -v && uv run mypy && uv run lint-imports`
Expected: PASS (tests pass; mypy clean; "Contracts: 2 kept, 0 broken").

- [ ] **Step 6: Smoke-test the server starts (stdio)**

Run: `echo '' | uv run python -m mcp_server` then press Ctrl-C after ~1s.
Expected: it starts and waits on stdio without error (no traceback). It will hang waiting for input — that is correct for an MCP stdio server.

- [ ] **Step 7: Commit**

```bash
git add mcp_server tests/test_mcp_server.py
git commit -m "feat: add MCP server exposing Fathom + ClickUp tools"
```

---

## Task 6: Author the synthesis skill

**Files:**
- Create: `skills/meeting-to-task/SKILL.md`

- [ ] **Step 1: Write the skill** (`skills/meeting-to-task/SKILL.md`)

```markdown
---
name: meeting-to-task
description: Turn a Fathom meeting into a ClickUp task with recorded minutes, then confirm in Slack.
version: 1.0.0
metadata:
  hermes:
    tags: [clickup, fathom, synthesis]
    category: operations
---

# Meeting → ClickUp task

## When to Use
When a user shares a Fathom meeting link or recording id in Slack and wants the minutes
captured as a ClickUp task.

## Procedure
1. Extract the numeric `recording_id` from the Fathom link (the number in
   `fathom.video/calls/<id>` or a bare id).
2. Call `mcp_agentos_fathom_get_transcript` with that `recording_id`.
3. Synthesize structured minutes from the transcript in this markdown shape:
   - `## Summary` — 2-4 sentences.
   - `## Decisions` — bullet list.
   - `## Action items` — bullet list, each `owner — action`.
4. Call `mcp_agentos_clickup_create_task` with:
   - `list_id` = the configured POC list (env `CLICKUP_LIST_ID`).
   - `name` = `Minutes — <meeting topic or date>`.
   - `markdown_description` = the minutes from step 3.
5. Reply in Slack with a confirmation and the returned task `url`.

## Pitfalls
- Transcripts lag a few minutes after a meeting ends; if the API returns empty, wait and retry.
- Never invent action items not present in the transcript.

## Verification
- The Slack reply contains a clickable ClickUp task URL.
- Opening the task shows the Summary / Decisions / Action items sections.
```

- [ ] **Step 2: Lint the markdown**

Run: `npx -y markdownlint-cli2 "skills/**/*.md"`
Expected: PASS. (If MD025/frontmatter rules complain, they are disabled in `.markdownlint.jsonc` from Plan 1; otherwise fix.)

- [ ] **Step 3: Commit**

```bash
git add skills/meeting-to-task/SKILL.md
git commit -m "feat: add meeting-to-task synthesis skill"
```

---

## Task 7: ADR-0002 + import-linter still green

**Files:**
- Create: `docs/adr/0002-external-apis.md`

- [ ] **Step 1: Write the ADR** (`docs/adr/0002-external-apis.md`)

```markdown
# ADR-0002: External APIs via typed clients; secrets from env

- **Status:** accepted
- **Date:** 2026-06-07

## Rule
External HTTP APIs (Fathom, ClickUp) are accessed only through their typed client modules
(`tools/fathom/client.py`, `clickup/client.py`). API keys/tokens are read only from environment
variables — never hardcoded or passed through Slack messages.

## Why
Centralizes auth, timeouts, and error handling; keeps secrets out of source and logs; makes the
MCP tools thin and testable.

## Scope
`tools/`, `clickup/`, `mcp_server/`.

## Enforcement
`import-linter` keeps tools/clickup boundaries; secret-from-env is verified in code review and
by the absence of literals in tests (tests inject via `monkeypatch.setenv` / constructor token).
```

- [ ] **Step 2: Run spec + architecture checks**

Run: `uv run python scripts/check_specs.py && uv run lint-imports`
Expected: PASS (spec OK; contracts kept).

- [ ] **Step 3: Commit**

```bash
git add docs/adr/0002-external-apis.md
git commit -m "docs: add ADR-0002 external APIs via typed clients"
```

---

## Task 8: Deployment — docker-compose for Unraid + MCP registration

**Files:**
- Create: `deploy/.env.example`
- Create: `deploy/hermes-config.yaml`
- Create: `deploy/docker-compose.yml`

- [ ] **Step 1: Create the env template** (`deploy/.env.example`)

```bash
# Copy to deploy/.env on the Unraid host and fill in. deploy/.env is gitignored.
FATHOM_API_KEY=
CLICKUP_TOKEN=
CLICKUP_LIST_ID=
# Slack tokens are set interactively via `hermes gateway setup` and stored in the
# persistent /root/.hermes volume.
```

- [ ] **Step 2: Create the Hermes MCP config** (`deploy/hermes-config.yaml`)

```yaml
# Mounted into the Hermes config dir. Registers our in-repo MCP server.
# Tools appear to the agent as mcp_agentos_<tool>.
mcp_servers:
  agentos:
    command: "uv"
    args: ["run", "--directory", "/opt/agent-os", "python", "-m", "mcp_server"]
    env:
      FATHOM_API_KEY: "${FATHOM_API_KEY}"
      CLICKUP_TOKEN: "${CLICKUP_TOKEN}"

skills:
  external_dirs:
    - "/opt/agent-os/skills"
```

- [ ] **Step 3: Create the compose file** (`deploy/docker-compose.yml`)

```yaml
services:
  hermes:
    image: ghcr.io/nousresearch/hermes-agent:latest
    container_name: agent-os-hermes
    restart: unless-stopped
    env_file: .env
    volumes:
      - hermes_data:/root/.hermes            # persistent memory + skills + gateway creds
      - ./hermes-config.yaml:/root/.hermes/config.d/agentos.yaml:ro
      - ../:/opt/agent-os:ro                  # this repo (MCP server + skills)
    # Slack gateway runs inside this container; configure once with `hermes gateway setup`.

volumes:
  hermes_data:
```

- [ ] **Step 4: Add `deploy/.env` to gitignore**

Append to `.gitignore`:

```
deploy/.env
```

- [ ] **Step 5: Validate compose + config locally**

Run: `docker compose -f deploy/docker-compose.yml config >/dev/null && echo "compose ok"`
Run: `uv run python -c "import yaml; yaml.safe_load(open('deploy/hermes-config.yaml')); print('config ok')"`
Expected: `compose ok` then `config ok`.

> Note: the exact Hermes image tag and config-mount path must be confirmed against the Hermes
> docs (`/docs/user-guide/...` and `hermes docker-compose`) when the tech lead deploys; adjust the image
> and the `config.d` path if Hermes expects a single `config.yaml`. The MCP block and skills dir
> are the parts we own.

- [ ] **Step 6: Commit**

```bash
git add deploy/ .gitignore
git commit -m "feat: add Unraid docker-compose, MCP registration, env template"
```

---

## Task 9: End-to-end manual verification (the demo)

**Files:** none (runbook). Owner: Tech lead.

- [ ] **Step 1: Configure secrets on the Unraid host**

Copy `deploy/.env.example` → `deploy/.env`, fill `FATHOM_API_KEY`, `CLICKUP_TOKEN`,
`CLICKUP_LIST_ID`. Get the list id from ClickUp (open the POC list; the id is in the URL or via
`clickup-core-workflow-b`).

- [ ] **Step 2: Bring up the stack**

Run: `cd deploy && docker compose up -d && docker compose logs -f hermes`
Expected: Hermes starts; logs show the `agentos` MCP server registered and tools
`mcp_agentos_fathom_get_transcript`, `mcp_agentos_clickup_create_task`,
`mcp_agentos_clickup_add_comment` discovered.

- [ ] **Step 3: Configure Slack**

Run (inside the container): `docker compose exec hermes hermes gateway setup` → select Slack →
provide bot token + app-level token. Confirm the gateway starts.

- [ ] **Step 4: Run the loop from Slack**

In the configured Slack channel/DM, send the co-pilot a real Fathom meeting link
(e.g. one of your own recordings). Ask it to "capture the minutes as a ClickUp task."

- [ ] **Step 5: Verify the outcome (spec success criterion #1)**

Expected:
- The agent replies in Slack with a ClickUp task URL.
- The task exists in the POC list with `## Summary`, `## Decisions`, `## Action items`.
- The minutes need no manual correction on a real meeting.

- [ ] **Step 6: Record the result**

Capture a short Loom/screenshot of the loop for the demo and link it in the POC PRD
(`docs/prd/poc-meeting-to-task.md`).

---

## Task 10: README update + final verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add a "Run the co-pilot" section to `README.md`**

```markdown
## Run the co-pilot (Track A)
1. Fill `deploy/.env` from `deploy/.env.example` (Fathom + ClickUp keys, POC list id).
2. `cd deploy && docker compose up -d`
3. `docker compose exec hermes hermes gateway setup` → Slack.
4. In Slack, send the co-pilot a Fathom meeting link and ask for the minutes.
The synthesis lives in `skills/meeting-to-task/SKILL.md`; tools in `mcp_server/`.
```

- [ ] **Step 2: Run the entire harness + tests**

Run: `uv run pre-commit run --all-files && uv run pytest -v`
Expected: all hooks "Passed"; all tests PASS.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document running the Track A co-pilot"
```

---

## Self-Review Notes (verified against the spec)

- **§4 Component: Hermes runtime + Slack** → Task 8 (compose, gateway), Task 9 (gateway setup).
- **§4 Component: Fathom tool** → Task 2 (real Fathom API client).
- **§4 Component: ClickUp client** → Tasks 3, 4 (create_task + add_comment, ClickUp v2).
- **§4 Component: Synthesis skill** → Task 6 (`SKILL.md`, self-improving).
- **§3 MCP integration** → Task 5 (MCP server) + Task 8 (`config.yaml` registration → `mcp_agentos_*`).
- **§3 ADR boundaries hold** → fathom client never imports clickup; both reached only via MCP server / clients; verified by `lint-imports` in Tasks 5, 7.
- **§11 success criterion #1** (loop completes unaided, minutes accurate) → Task 9 Step 5.
- **Type consistency:** `Transcript(recording_id:int, text:str)` and `TaskRef(id:str, url:str)` used identically in client, MCP server, and tests. (Note: this changes the Plan 1 stub signature from `meeting_id:str` to `recording_id:int` — done in Task 2 Step 3.)
- **Deferred to roadmap (Phase 1+):** ClickUp webhooks/Goals, Google Workspace, dashboards, multi-instance — not in this plan by design.
```
