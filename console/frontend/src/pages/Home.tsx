import { Loader2, Mail, MailX, Map, PlugZap, RefreshCw } from "lucide-react"
import { useState } from "react"

import type { View } from "@/App"
import { MailChat } from "@/components/MailChat"
import { MailMindmap } from "@/components/MailMindmap"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { type MailNode, getMailTree, reloadMail } from "@/lib/brainApi"

const WINDOW_OPTIONS = [
  { label: "Last 15 minutes", minutes: 15 },
  { label: "Last 30 minutes", minutes: 30 },
  { label: "Last 1 hour", minutes: 60 },
  { label: "Last 3 hours", minutes: 180 },
]

interface HomeRail {
  appsConnected: number
  appsTotal: number
  mailThreads: number | null
  mailConnected: boolean | null
}

export function Home({ rail, onNavigate }: { rail: HomeRail; onNavigate: (view: View) => void }) {
  return (
    <div className="flex flex-col gap-6">
      <div className="grid gap-4 sm:grid-cols-2">
        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Connected apps
            </CardTitle>
            <PlugZap className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-semibold">
              {rail.appsConnected}
              <span className="text-lg text-muted-foreground"> / {rail.appsTotal}</span>
            </p>
            <button
              type="button"
              onClick={() => onNavigate("applications")}
              className="text-sm text-primary underline-offset-4 hover:underline"
            >
              Manage connected apps
            </button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Your mail
            </CardTitle>
            <Mail className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-semibold">
              {rail.mailThreads === null ? "—" : rail.mailThreads}
            </p>
            <p className="text-sm text-muted-foreground">conversations organized</p>
          </CardContent>
        </Card>
      </div>

      {rail.mailConnected === false ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
            <MailX className="h-10 w-10 text-muted-foreground" />
            <div>
              <p className="font-medium">Gmail isn't connected</p>
              <p className="mt-1 text-sm text-muted-foreground">
                Connect Gmail from the Connected apps tab to see your mail here.
              </p>
            </div>
          </CardContent>
        </Card>
      ) : (
        <MailPanel />
      )}
    </div>
  )
}

function MailPanel() {
  const [windowMinutes, setWindowMinutes] = useState(WINDOW_OPTIONS[0].minutes)
  const [reloading, setReloading] = useState(false)
  const [reloadResult, setReloadResult] = useState<string | null>(null)
  const [reloadError, setReloadError] = useState<string | null>(null)

  const [showMindmap, setShowMindmap] = useState(false)
  const [treeLoading, setTreeLoading] = useState(false)
  const [treeError, setTreeError] = useState<string | null>(null)
  const [tree, setTree] = useState<MailNode | null>(null)

  async function handleReload() {
    setReloading(true)
    setReloadError(null)
    setReloadResult(null)
    try {
      const result = await reloadMail(windowMinutes)
      setReloadResult(`Found ${result.processed} new email${result.processed === 1 ? "" : "s"}.`)
      if (showMindmap) {
        const updated = await getMailTree()
        setTree(updated)
      }
    } catch (err) {
      setReloadError(err instanceof Error ? err.message : "Couldn't check for new mail.")
    } finally {
      setReloading(false)
    }
  }

  async function handleShowMindmap() {
    if (showMindmap) {
      setShowMindmap(false)
      return
    }
    setShowMindmap(true)
    if (tree) return
    setTreeLoading(true)
    setTreeError(null)
    try {
      const data = await getMailTree()
      setTree(data)
    } catch (err) {
      setTreeError(err instanceof Error ? err.message : "Couldn't load your mail map.")
    } finally {
      setTreeLoading(false)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader className="flex-row flex-wrap items-center justify-between gap-3">
          <CardTitle>Your mail</CardTitle>
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={windowMinutes}
              onChange={(e) => setWindowMinutes(Number(e.target.value))}
              className="h-9 rounded-md border border-input px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {WINDOW_OPTIONS.map((opt) => (
                <option key={opt.minutes} value={opt.minutes}>
                  {opt.label}
                </option>
              ))}
            </select>
            <Button onClick={handleReload} disabled={reloading} size="sm">
              {reloading ? (
                <Loader2 className="mr-1 h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="mr-1 h-4 w-4" />
              )}
              Check for new mail
            </Button>
            <Button onClick={handleShowMindmap} variant="outline" size="sm">
              <Map className="mr-1 h-4 w-4" />
              {showMindmap ? "Hide mail map" : "View mail map"}
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            New mail is also checked automatically every 4 hours.
          </p>
          {reloadResult && <p className="mt-2 text-sm text-primary">{reloadResult}</p>}
          {reloadError && <p className="mt-2 text-sm text-destructive">{reloadError}</p>}
        </CardContent>
      </Card>

      {showMindmap && (
        <Card>
          <CardContent className="pt-6">
            {treeLoading && <p className="text-sm text-muted-foreground">Loading your mail map…</p>}
            {treeError && <p className="text-sm text-destructive">{treeError}</p>}
            {tree && <MailMindmap data={tree} />}
          </CardContent>
        </Card>
      )}

      <div className="max-w-[420px]">
        <MailChat />
      </div>
    </div>
  )
}
