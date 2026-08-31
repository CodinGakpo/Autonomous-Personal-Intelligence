// Talks to brain/viz_server.py (the mail knowledge-tree service, port 8080) — a separate
// backend from console/backend (port 8000, see src/api.ts). Kept in its own module since it's
// a different service with its own base URL, not part of the ops-console API surface.

const BASE_URL: string = import.meta.env.VITE_BRAIN_API_BASE_URL ?? "http://localhost:8080"

export interface MailNode {
  id: string
  name: string
  type: "root" | "mail_category" | "mail_topic" | "mail_thread"
  summary?: string | null
  body?: string | null
  source_uids?: string[]
  children?: MailNode[]
}

export interface MailReloadResult {
  processed: number
  results: Array<Record<string, unknown>>
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  headers.set("Content-Type", "application/json")
  const res = await fetch(`${BASE_URL}${path}`, { ...init, headers })
  if (!res.ok) {
    const detail = await res.text()
    throw new Error(detail || res.statusText)
  }
  return (await res.json()) as T
}

export function getMailTree(): Promise<MailNode> {
  return request<MailNode>("/api/mail_tree")
}

export function reloadMail(sinceMinutes: number): Promise<MailReloadResult> {
  return request<MailReloadResult>("/api/mail/reload", {
    method: "POST",
    body: JSON.stringify({ since_minutes: sinceMinutes }),
  })
}

export function getMailStatus(): Promise<{ connected: boolean }> {
  return request<{ connected: boolean }>("/api/mail/status")
}

export function disconnectMail(): Promise<{ connected: boolean }> {
  return request<{ connected: boolean }>("/api/mail/disconnect", { method: "POST" })
}

// Opens the OAuth consent browser tab on the machine running this server and blocks until
// the person finishes (or abandons) it — see brain/viz_server.py's mail_connect().
export function connectMail(): Promise<{ connected: boolean }> {
  return request<{ connected: boolean }>("/api/mail/connect", { method: "POST" })
}

export interface MailAskProfileDetail {
  key: string
  value: string
}

export interface MailAskResponse {
  answer: string
}

export function askMail(
  question: string,
  profileDetails: MailAskProfileDetail[],
): Promise<MailAskResponse> {
  return request<MailAskResponse>("/api/mail/ask", {
    method: "POST",
    body: JSON.stringify({ question, profile_details: profileDetails }),
  })
}
