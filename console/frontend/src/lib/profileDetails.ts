// Shared "About you" details storage: Profile.tsx edits it, MailChat.tsx reads it to fold
// into mail-ask requests as light personal context. Kept out of pages/ so a component
// doesn't import from a page module.
export interface ProfileDetail {
  id: string
  key: string
  value: string
}

const STORAGE_KEY = "agent-os:profile-details"

export function loadProfileDetails(): ProfileDetail[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as ProfileDetail[]) : []
  } catch {
    return []
  }
}

export function saveProfileDetails(details: ProfileDetail[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(details))
  } catch {
    // Private browsing / storage disabled — details just won't persist across visits.
  }
}
