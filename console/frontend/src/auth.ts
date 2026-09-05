// Token and role storage — kept in localStorage for SPA convenience.
// Neither token nor role are sensitive enough to warrant a different store in this demo context.

const TOKEN_KEY = "ops_token"
const ROLE_KEY = "ops_role"

// A tiny pub-sub so App.tsx can notice when a 401 from either API client (api.ts or
// brainApi.ts) clears the token out from under it, without prop-drilling every API call
// through a shared state manager for what's fundamentally one boolean.
type AuthListener = () => void
const listeners = new Set<AuthListener>()

export function onAuthChange(cb: AuthListener): () => void {
  listeners.add(cb)
  return () => listeners.delete(cb)
}

function notify(): void {
  for (const cb of listeners) cb()
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(t: string): void {
  localStorage.setItem(TOKEN_KEY, t)
  notify()
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(ROLE_KEY)
  notify()
}

// Access role — populated from GET /auth/me after login.
export type AccessRole = "admin" | "team_lead" | "developer" | "hr"

export function getRole(): AccessRole | null {
  return localStorage.getItem(ROLE_KEY) as AccessRole | null
}

export function setRole(r: AccessRole): void {
  localStorage.setItem(ROLE_KEY, r)
}

export function isPrivileged(): boolean {
  const r = getRole()
  return r === "admin" || r === "team_lead" || r === "hr"
}
