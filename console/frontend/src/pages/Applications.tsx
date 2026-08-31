import { Check, Clock, ExternalLink, Plug, Plus } from "lucide-react"
import { useEffect, useState } from "react"

import { type Application, AVAILABLE_APPS, CORE_APPS, GMAIL_APP, connectApp, disconnectApp, getHealth } from "@/api"
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
import { connectMail, disconnectMail, getMailStatus } from "@/lib/brainApi"

/**
 * One app, shown as a card with an inline "set up" flow.
 *
 * BACKEND DEV: clicking "Set up" calls `connectApp(id, credential)` →
 * POST /applications/{id}/connect, which DOES NOT EXIST yet. Until you build it, the
 * call 404s and we surface a "pending backend" note (so the page still demos). Once the
 * endpoint is live, a token app stores the secret + flips to Connected; an OAuth app
 * returns { authUrl } and we redirect the browser to start the OAuth flow.
 *
 * Gmail is the exception: it's connected through a separate service (brain/emailtool.py),
 * so its disconnect actually works today — it revokes the cached OAuth token.
 */
function AppCard({ id, name, description, connected, kind, credentialLabel, onChanged }: Application & { onChanged?: () => void }) {
  const [open, setOpen] = useState(false)
  const [credential, setCredential] = useState("")
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<string | null>(null)
  const [done, setDone] = useState(connected)

  useEffect(() => setDone(connected), [connected])

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
      setNote("Connecting this app isn't available yet.")
    } finally {
      setBusy(false)
    }
  }

  async function connectGmail() {
    setBusy(true)
    setNote(null)
    try {
      const res = await connectMail()
      setDone(res.connected)
      if (!res.connected) setNote("Authorization wasn't completed — try again.")
      onChanged?.()
    } catch {
      setNote("Couldn't reach the mail service — is it running?")
    } finally {
      setBusy(false)
    }
  }

  async function disconnect() {
    setBusy(true)
    setNote(null)
    try {
      if (id === "gmail") {
        const res = await disconnectMail()
        setDone(res.connected)
      } else {
        await disconnectApp(id)
        setDone(false)
      }
      onChanged?.()
    } catch {
      setNote("Disconnecting this app isn't available yet.")
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
          <Badge variant="caution">
            <Clock className="mr-1 h-3 w-3" />
            Not connected
          </Badge>
        )}
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {id === "gmail" && !done && (
          <p className="text-sm text-muted-foreground">
            Opens a Google sign-in tab to connect — no terminal needed.
          </p>
        )}
        {id === "gmail" ? (
          <div className="flex gap-2">
            {!done && (
              <Button size="sm" onClick={connectGmail} disabled={busy}>
                {busy ? "Waiting for authorization…" : "Connect"}
              </Button>
            )}
            {done && (
              <Button size="sm" variant="ghost" onClick={disconnect} disabled={busy}>
                {busy ? "Disconnecting…" : "Disconnect"}
              </Button>
            )}
          </div>
        ) : !open ? (
          <div className="flex gap-2">
            <Button
              size="sm"
              variant={done ? "outline" : "default"}
              onClick={() => setOpen(true)}
            >
              {done ? "Manage" : "Set up"}
            </Button>
            {done && (
              <Button size="sm" variant="ghost" onClick={disconnect} disabled={busy}>
                {busy ? "Disconnecting…" : "Disconnect"}
              </Button>
            )}
          </div>
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
                You'll be asked to sign in to {name} to connect it.{" "}
                <ExternalLink className="inline h-3 w-3" />
              </p>
            )}
            <div className="flex gap-2">
              <Button size="sm" onClick={submit} disabled={busy}>
                {busy ? "Connecting…" : "Connect"}
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
          </div>
        )}
        {note && <p className="text-sm text-muted-foreground">{note}</p>}
      </CardContent>
    </Card>
  )
}

/**
 * Applications page: shows every integration and lets you set up or disconnect it.
 *
 * BACKEND DEV: live connected-status for the 3 core apps comes from GET /health today. To make
 * this fully data-driven (and to support the "available" apps), implement GET /applications and
 * have it return every app + its `connected` state — then this page can drop the hardcoded
 * CORE_APPS / AVAILABLE_APPS fallbacks in api.ts.
 */
export function Applications({ onMailStatusChange }: { onMailStatusChange?: () => void }) {
  const [statuses, setStatuses] = useState<Record<string, boolean> | null>(null)
  const [gmailConnected, setGmailConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getHealth()
      .then((h) =>
        setStatuses(
          Object.fromEntries(h.integrations.map((i) => [i.name, i.status === "configured"])),
        ),
      )
      .catch(() => setError("Could not load applications."))

    getMailStatus()
      .then((s) => setGmailConnected(s.connected))
      .catch(() => setGmailConnected(false))
  }, [])

  if (error) return <p className="text-sm text-destructive">{error}</p>
  if (!statuses) return <p className="text-sm text-muted-foreground">Loading…</p>

  function handleChanged() {
    getMailStatus()
      .then((s) => setGmailConnected(s.connected))
      .catch(() => setGmailConnected(false))
    onMailStatusChange?.()
  }

  // Every app in one list, then split by whether it's actually connected — apps move
  // between sections as their real status changes, instead of a fixed "core" tier.
  const all: Application[] = [
    { ...GMAIL_APP, connected: gmailConnected },
    ...Object.entries(CORE_APPS).map(([id, meta]) => ({
      id,
      ...meta,
      connected: statuses[id] ?? false,
    })),
    ...AVAILABLE_APPS,
  ]
  const connected = all.filter((a) => a.connected)
  const notConnected = all.filter((a) => !a.connected)

  return (
    <div className="flex flex-col gap-8">
      {connected.length > 0 && (
        <section className="flex flex-col gap-3">
          <div className="flex items-center gap-2">
            <Plug className="h-4 w-4 text-muted-foreground" />
            <h2 className="text-sm font-semibold text-foreground">Connected</h2>
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {connected.map((app) => (
              <AppCard key={app.id} {...app} onChanged={handleChanged} />
            ))}
          </div>
        </section>
      )}

      <section className="flex flex-col gap-3">
        <div className="flex items-center gap-2">
          <Plus className="h-4 w-4 text-muted-foreground" />
          <h2 className="text-sm font-semibold text-foreground">Add an app</h2>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {notConnected.map((app) => (
            <AppCard key={app.id} {...app} onChanged={handleChanged} />
          ))}
        </div>
      </section>
    </div>
  )
}
