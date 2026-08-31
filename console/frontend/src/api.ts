// The ONLY module that talks to the backend (ADR-0002). No third-party API calls here.
import { type AccessRole, clearToken, getToken } from "@/auth"

const BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000"

// ---------------------------------------------------------------------------
// DEMO MODE — works entirely in-browser with no backend, and has no seeded accounts.
// Set VITE_API_BASE_URL to a real server to disable this.
// ---------------------------------------------------------------------------
const DEMO_MODE = !import.meta.env.VITE_API_BASE_URL

function delay(ms = 400) { return new Promise((r) => setTimeout(r, ms)) }

export type IntegrationStatus = "configured" | "not_configured"

export interface IntegrationHealth {
  name: string
  status: IntegrationStatus
}

export interface HealthReport {
  ok: boolean
  integrations: IntegrationHealth[]
}

// Org / display roles (what the person does in the company).
export type OrgRole = "admin" | "team_lead" | "developer" | "intern" | "gtm" | "sales" | "hr"

export type Product = "product_one" | "product_two" | "product_three"

// Roster entry returned by GET /roster/me — sensitive fields may be null for developers.
export interface RosterEntry {
  name: string
  email: string | null         // null when caller is a developer viewing a peer
  role: OrgRole
  slack_handle: string
  products: Product[]
  clickup_task_id: string | null
  clickup_url: string | null
  is_own: boolean              // true when this row is the caller's own entry
}

export interface UserMe {
  id: number
  email: string
  role: AccessRole
}

// Parsed résumé — mirrors the talent-radar schema from tools/resume/parser.py
export interface RadarAxis {
  score: number
  evidence: string | null
}

export interface ResumeData {
  schema_version: string
  parse_confidence: number
  name: string | null
  email: string | null
  headline: string | null
  summary: string | null
  total_years_experience: number | null
  seniority: string | null
  skills: string[]
  strengths: string[]
  domains: string[]
  roles: Array<{
    company: string | null
    title: string | null
    start: string | null
    end: string | null
    months: number | null
    highlights: string[]
  }>
  education: Array<{
    degree: string | null
    field: string | null
    institution: string | null
    year: number | null
  }>
  certifications: string[]
  achievements: string[]
  radar: Record<string, RadarAxis>
  flags: string[]
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  headers.set("Content-Type", "application/json")
  const token = getToken()
  if (token) headers.set("Authorization", `Bearer ${token}`)

  const res = await fetch(`${BASE_URL}${path}`, { ...init, headers })
  if (res.status === 401) {
    clearToken()
    throw new ApiError(401, "Not authenticated")
  }
  if (!res.ok) {
    const detail = await res.text()
    throw new ApiError(res.status, detail || res.statusText)
  }
  return (await res.json()) as T
}

export async function login(email: string, password: string): Promise<string> {
  if (DEMO_MODE) {
    await delay()
    // No seeded accounts in demo mode — point VITE_API_BASE_URL at a real backend to sign in.
    throw new ApiError(401, "Sign-in needs a connected backend (set VITE_API_BASE_URL).")
  }
  const data = await request<{ token: string }>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  })
  return data.token
}

export async function getMe(): Promise<UserMe> {
  if (DEMO_MODE) {
    await delay(200)
    throw new ApiError(401, "Not authenticated")
  }
  return request<UserMe>("/auth/me")
}

export async function getHealth(): Promise<HealthReport> {
  if (DEMO_MODE) {
    await delay(300)
    // Nothing is actually connected until you set the real tokens (see SETUP.md).
    return {
      ok: false,
      integrations: [
        { name: "clickup", status: "not_configured" },
        { name: "slack",   status: "not_configured" },
        { name: "fathom",  status: "not_configured" },
      ],
    }
  }
  return request<HealthReport>("/health")
}

export async function getMyProfile(): Promise<RosterEntry> {
  if (DEMO_MODE) {
    await delay(200)
    throw new ApiError(404, "Profile not found")
  }
  return request<RosterEntry>("/roster/me")
}

/**
 * Fetch the parsed résumé for an employee.
 * Developers can only fetch their own (backend enforces with 403).
 */
export async function getResume(email: string): Promise<ResumeData> {
  if (DEMO_MODE) {
    await delay(400)
    throw new ApiError(404, `No résumé on file for ${email} in demo mode.`)
  }
  return request<ResumeData>(`/resume?email=${encodeURIComponent(email)}`)
}

// ===========================================================================
// Applications (integration setup) — the "Applications" page (formerly "Health")
//
// ⚠️ BACKEND DEV: the connect/disconnect endpoints below DO NOT EXIST YET.
// Today the backend only exposes GET /health (read-only status of the 3 core apps).
// To let HR *set up* apps from the UI, please implement:
//
//   GET  /applications
//     → Application[]  — the full catalog (core + available) with live `connected` state.
//       v1 may derive the 3 core apps from the existing /health check. Until this exists
//       the frontend falls back to the hardcoded CORE_APPS / AVAILABLE_APPS below.
//
//   POST /applications/{id}/connect    body: { credential: string }
//     → For a "token" app: validate the token, STORE IT SECURELY server-side
//       (env / secret store — NEVER return it to the browser), mark the app connected.
//       For an "oauth" app (Slack, Google): ignore `credential`, instead return
//       { authUrl } and let the browser redirect to begin the OAuth flow; the callback
//       endpoint stores the resulting token. Return 200 + the updated Application.
//
//   POST /applications/{id}/disconnect
//     → remove the stored credential, mark disconnected. Return 200.
//
// SECURITY: credentials only ever travel browser → backend (HTTPS), are stored as
// secrets, and are never sent back down. This honors ADR-0002 (no third-party SDKs/
// tokens in the browser) — the frontend only ever talks to OUR backend.
// ===========================================================================

export type AppConnectKind = "token" | "oauth"

export interface Application {
  id: string // stable key: "clickup", "slack", "fathom", "google_calendar", …
  name: string // display name
  description: string // one-liner shown on the card
  connected: boolean
  kind: AppConnectKind // "token" → show a credential field; "oauth" → redirect flow
  credentialLabel?: string // e.g. "API token" (only for kind === "token")
}

// The 3 core integrations tracked by the ops backend. Live connected-status comes from
// getHealth(); this is just the display metadata. BACKEND: fold these into GET /applications
// when you build it.
export const CORE_APPS: Record<string, Omit<Application, "id" | "connected">> = {
  clickup: { name: "ClickUp", description: "Create tasks and record meeting minutes.", kind: "token", credentialLabel: "API token" },
  slack: { name: "Slack", description: "Notifications and the Hermes agent gateway.", kind: "oauth" },
  fathom: { name: "Fathom", description: "Fetch meeting transcripts.", kind: "token", credentialLabel: "API key" },
}

// Gmail is wired up separately from this backend (see brain/emailtool.py's OAuth flow, not
// this backend's /health) — its live connected state comes from brainApi.getMailStatus(),
// not from here. `connected: false` is just the fallback before that status loads.
export const GMAIL_APP: Omit<Application, "connected"> = {
  id: "gmail",
  name: "Gmail",
  description: "Reads unread mail into the knowledge tree (see the Home tab).",
  kind: "oauth",
}

// Additional apps HR can connect. BACKEND: this hardcoded catalog is a placeholder — replace
// with GET /applications once that endpoint exists. Each needs a matching connect handler.
export const AVAILABLE_APPS: Application[] = [
  { id: "google_calendar", name: "Google Calendar", description: "Auto-detect meetings to capture.", connected: false, kind: "oauth" },
  { id: "notion", name: "Notion", description: "Sync docs and the knowledge base.", connected: false, kind: "token", credentialLabel: "Integration token" },
  { id: "hubspot", name: "HubSpot", description: "Sync CRM contacts and deals.", connected: false, kind: "token", credentialLabel: "Private app token" },
]

// BACKEND TODO: implement POST /applications/{id}/connect (see the block above).
// For "token" apps pass the secret; for "oauth" apps pass "" and expect { authUrl } back.
export function connectApp(id: string, credential: string): Promise<{ authUrl?: string }> {
  return request<{ authUrl?: string }>(`/applications/${id}/connect`, {
    method: "POST",
    body: JSON.stringify({ credential }),
  })
}

// BACKEND TODO: implement POST /applications/{id}/disconnect (remove the stored secret).
export function disconnectApp(id: string): Promise<void> {
  return request<void>(`/applications/${id}/disconnect`, { method: "POST" })
}


