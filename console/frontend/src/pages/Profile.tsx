// A free-form list of facts about you, stored server-side against your account.
//
// It used to live in localStorage, which meant the mail pipeline could never read it — and the
// pipeline is exactly where it matters: attachment scanning happens at ingest, headless, so
// "is my name on this shortlist?" is only answerable if your name is stored where the ingest
// can reach it. Identity-ish rows (Name, Roll no, Neo ID, …) become attachment identifiers;
// see brain/profile.py's IDENTITY_KEYS.
import { Loader2, Plus, Trash2, UserCircle2 } from "lucide-react"
import { useEffect, useState } from "react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { type ProfileDetailPayload, getProfile, saveProfile } from "@/lib/brainApi"
import { loadProfileDetails, saveProfileDetails } from "@/lib/profileDetails"

interface Detail extends ProfileDetailPayload {
  id: string
}

const withIds = (details: ProfileDetailPayload[]): Detail[] =>
  details.map((d) => ({ ...d, id: crypto.randomUUID() }))

export function Profile() {
  const [details, setDetails] = useState<Detail[]>([])
  const [identifiers, setIdentifiers] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [newKey, setNewKey] = useState("")
  const [newValue, setNewValue] = useState("")

  useEffect(() => {
    let cancelled = false
    getProfile()
      .then(async (result) => {
        if (cancelled) return
        // One-time carry-over: anything still in this browser's localStorage moves to the
        // account the first time the server has nothing, then the local copy is dropped.
        const local = loadProfileDetails()
        if (result.details.length === 0 && local.length > 0) {
          const migrated = await saveProfile(local.map(({ key, value }) => ({ key, value })))
          if (cancelled) return
          saveProfileDetails([])
          setDetails(withIds(migrated.details))
          setIdentifiers(migrated.identifiers)
          return
        }
        setDetails(withIds(result.details))
        setIdentifiers(result.identifiers)
      })
      .catch(() => {
        if (!cancelled) setError("Couldn't load your details.")
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  async function persist(next: Detail[]) {
    setDetails(next) // optimistic: the list is the user's own edit
    setSaving(true)
    setError(null)
    try {
      const result = await saveProfile(next.map(({ key, value }) => ({ key, value })))
      setIdentifiers(result.identifiers)
    } catch {
      setError("Couldn't save — your last change may not have stuck.")
    } finally {
      setSaving(false)
    }
  }

  function addDetail() {
    const key = newKey.trim()
    const value = newValue.trim()
    if (!key || !value) return
    void persist([...details, { id: crypto.randomUUID(), key, value }])
    setNewKey("")
    setNewValue("")
  }

  function removeDetail(id: string) {
    void persist(details.filter((d) => d.id !== id))
  }

  return (
    <Card className="max-w-lg">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <UserCircle2 className="h-5 w-5 text-muted-foreground" />
          About you
          {saving && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
        </CardTitle>
        <p className="text-sm text-muted-foreground">
          Add details you want the assistant to know when it answers your questions — your name,
          timezone, role, whatever's useful. Saved to your account.
        </p>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {error && <p className="text-sm text-destructive">{error}</p>}

        {loading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : details.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            You haven't added anything yet — try "Name", "Roll no", or "Timezone" below.
          </p>
        ) : (
          <ul className="flex flex-col divide-y divide-border">
            {details.map((d) => (
              <li key={d.id} className="flex items-center justify-between gap-3 py-2.5">
                <div className="flex min-w-0 flex-col">
                  <span className="text-sm font-medium">{d.key}</span>
                  <span className="truncate text-sm text-muted-foreground">{d.value}</span>
                </div>
                <Button
                  size="icon"
                  variant="ghost"
                  onClick={() => removeDetail(d.id)}
                  aria-label={`Remove ${d.key}`}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </li>
            ))}
          </ul>
        )}

        <div className="flex flex-col gap-2 rounded-lg border border-dashed border-input p-3">
          <div className="flex gap-2">
            <Input
              value={newKey}
              onChange={(e) => setNewKey(e.target.value)}
              placeholder="Label (e.g. Roll no)"
              className="w-2/5"
              aria-label="Detail label"
            />
            <Input
              value={newValue}
              onChange={(e) => setNewValue(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addDetail()}
              placeholder="Detail (e.g. 23BCE1234)"
              aria-label="Detail value"
            />
          </div>
          <Button
            size="sm"
            variant="outline"
            onClick={addDetail}
            disabled={!newKey.trim() || !newValue.trim()}
            className="self-start"
          >
            <Plus className="mr-1 h-4 w-4" />
            Add detail
          </Button>
        </div>

        <div className="rounded-lg bg-muted p-3 text-sm" data-testid="identifier-summary">
          {identifiers.length > 0 ? (
            <>
              <span className="text-muted-foreground">Looked for inside attachments: </span>
              <span className="font-medium">{identifiers.join(", ")}</span>
            </>
          ) : (
            <span className="text-muted-foreground">
              Add a <b>Name</b>, <b>Roll no</b> or <b>Neo ID</b> and the assistant will check
              whether spreadsheets and PDFs attached to your mail mention you.
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
