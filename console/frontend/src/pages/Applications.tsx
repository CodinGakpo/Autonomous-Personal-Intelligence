import { Check, ExternalLink, Plug, Plus } from "lucide-react"
import { useEffect, useState } from "react"

import { type Application, AVAILABLE_APPS, CORE_APPS, connectApp, getHealth } from "@/api"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

/**
 * One app, shown as a card with an inline "set up" flow.
 *
 * BACKEND DEV: clicking "Set up" calls `connectApp(id, credential)` →
 * POST /applications/{id}/connect, which DOES NOT EXIST yet. Until you build it, the
 * call 404s and we surface a "pending backend" note (so the page still demos). Once the
 * endpoint is live, a token app stores the secret + flips to Connected; an OAuth app
 * returns { authUrl } and we redirect the browser to start the OAuth flow.
 */
function AppCard({ id, name, description, connected, kind, credentialLabel }: Application) {
  const [open, setOpen] = useState(false)
  const [credential, setCredential] = useState("")
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<string | null>(null)
  const [done, setDone] = useState(connected)

  async function submit() {
    setBusy(true)
    setNote(null)
    try {
      const res = await connectApp(id, kind === "token" ? credential : "")
      // OAuth apps: backend hands back a URL to redirect to and finish authorisation.
      if (res.authUrl) {
        window.location.href = res.authUrl
        return
      }
      setDone(true)
      setOpen(false)
    } catch {
      // POST /applications/{id}/connect isn't implemented yet — backend dev's task.
      setNote("Setup endpoint pending — the backend will wire this up.")
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-3">
        <div className="flex flex-col gap-1">
          <CardTitle className="text-base">{name}</CardTitle>
          <CardDescription>{description}</CardDescription>
        </div>
        {done ? (
          <Badge variant="default">
            <Check className="mr-1 h-3 w-3" />
            Connected
          </Badge>
        ) : (
          <Badge variant="secondary">Not connected</Badge>
        )}
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {!open ? (
          <Button
            size="sm"
            variant={done ? "outline" : "default"}
            onClick={() => setOpen(true)}
          >
            {done ? "Manage" : "Set up"}
          </Button>
        ) : (
          <div className="flex flex-col gap-2 rounded-md border border-input p-3">
            {kind === "token" ? (
              <>
                <Label htmlFor={`cred-${id}`}>{credentialLabel ?? "Credential"}</Label>
                <Input
                  id={`cred-${id}`}
                  type="password"
                  value={credential}
                  onChange={(e) => setCredential(e.target.value)}
                  placeholder="paste it here"
                />
              </>
            ) : (
              <p className="text-sm text-muted-foreground">
                {name} connects via OAuth — the backend will redirect you to authorise.{" "}
                <ExternalLink className="inline h-3 w-3" />
              </p>
            )}
            <div className="flex gap-2">
              <Button size="sm" onClick={submit} disabled={busy}>
                {busy ? "Connecting…" : kind === "token" ? "Connect" : "Continue with OAuth"}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  setOpen(false)
                  setNote(null)
                }}
              >
                Cancel
              </Button>
            </div>
            {note && <p className="text-sm text-muted-foreground">{note}</p>}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

/**
 * Applications page (renamed from "Health"): shows the integrations and lets HR set them up.
 *
 * BACKEND DEV: live connected-status for the 3 core apps comes from GET /health today. To make
 * this fully data-driven (and to support the "available" apps), implement GET /applications and
 * have it return every app + its `connected` state — then this page can drop the hardcoded
 * CORE_APPS / AVAILABLE_APPS fallbacks in api.ts.
 */
export function Applications() {
  const [statuses, setStatuses] = useState<Record<string, boolean> | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getHealth()
      .then((h) =>
        setStatuses(
          Object.fromEntries(h.integrations.map((i) => [i.name, i.status === "configured"])),
        ),
      )
      .catch(() => setError("Could not load applications."))
  }, [])

  if (error) return <p className="text-sm text-destructive">{error}</p>
  if (!statuses) return <p className="text-sm text-muted-foreground">Loading…</p>

  // The 3 core apps, with live connected-status overlaid from /health.
  const core: Application[] = Object.entries(CORE_APPS).map(([id, meta]) => ({
    id,
    ...meta,
    connected: statuses[id] ?? false,
  }))

  return (
    <div className="flex flex-col gap-8">
      <section className="flex flex-col gap-3">
        <div className="flex items-center gap-2">
          <Plug className="h-4 w-4 text-muted-foreground" />
          <h2 className="font-semibold">Connected apps</h2>
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          {core.map((app) => (
            <AppCard key={app.id} {...app} />
          ))}
        </div>
      </section>

      <section className="flex flex-col gap-3">
        <div className="flex items-center gap-2">
          <Plus className="h-4 w-4 text-muted-foreground" />
          <h2 className="font-semibold">Connect a new app</h2>
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          {AVAILABLE_APPS.map((app) => (
            <AppCard key={app.id} {...app} />
          ))}
        </div>
      </section>
    </div>
  )
}
