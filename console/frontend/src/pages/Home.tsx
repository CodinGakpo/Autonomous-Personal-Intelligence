import { Check, Loader2, Mail, MailX, Map, PlugZap, RefreshCw } from "lucide-react"
import type { ReactNode } from "react"
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

function StatCard({
  icon: Icon,
  iconClass,
  label,
  value,
  suffix,
  action,
  delay,
}: {
  icon: typeof Mail
  iconClass: string
  label: string
  value: ReactNode
  suffix?: ReactNode
  action?: ReactNode
  delay?: string
}) {
  return (
    <Card className="card-hover animate-fade-up" style={delay ? { animationDelay: delay } : undefined}>
      <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">{label}</CardTitle>
        <span className={["flex h-8 w-8 items-center justify-center rounded-lg", iconClass].join(" ")}>
          <Icon className="h-4 w-4" />
        </span>
      </CardHeader>
      <CardContent>
        <p className="text-3xl font-semibold tracking-tight">
          {value}
          {suffix}
        </p>
        {action}
      </CardContent>
    </Card>
  )
}

export function Home({ rail, onNavigate }: { rail: HomeRail; onNavigate: (view: View) => void }) {
  return (
    <div className="flex flex-col gap-6">
      <div className="grid gap-4 sm:grid-cols-2">
        <StatCard
          icon={PlugZap}
          iconClass="bg-accent text-primary"
          label="Connected apps"
          value={rail.appsConnected}
          suffix={<span className="text-lg text-muted-foreground"> / {rail.appsTotal}</span>}
          action={
            <button
              type="button"
              onClick={() => onNavigate("applications")}
              className="text-sm text-primary underline-offset-4 hover:underline"
            >
              Manage connected apps
            </button>
          }
        />

        <StatCard
          icon={Mail}
          iconClass="bg-emerald-50 text-emerald-600"
          label="Your mail"
          value={rail.mailThreads === null ? "—" : rail.mailThreads}
          action={<p className="text-sm text-muted-foreground">conversations organized</p>}
          delay="60ms"
        />
      </div>

      {rail.mailConnected === false ? (
        <Card className="animate-fade-up" style={{ animationDelay: "120ms" }}>
          <CardContent className="flex flex-col items-center gap-3 py-14 text-center">
            <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-muted text-muted-foreground">
              <MailX className="h-6 w-6" />
            </span>
            <div>
              <p className="font-medium">Gmail isn't connected</p>
              <p className="mx-auto mt-1 max-w-sm text-sm text-muted-foreground">
                Connect Gmail to see your mail organized here and ask questions about it.
              </p>
            </div>
            <Button size="sm" className="mt-1" onClick={() => onNavigate("applications")}>
              Connect Gmail
            </Button>
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
      <Card className="animate-fade-up" style={{ animationDelay: "120ms" }}>
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
          {reloadResult && (
            <p className="mt-2 flex items-center gap-1.5 text-sm text-emerald-600 animate-fade-up">
              <Check className="h-3.5 w-3.5" />
              {reloadResult}
            </p>
          )}
          {reloadError && <p className="mt-2 text-sm text-destructive animate-fade-up">{reloadError}</p>}
        </CardContent>
      </Card>

      {showMindmap && (
        <Card className="animate-fade-up overflow-hidden">
          <CardContent className="p-0">
            {treeLoading && (
              <div className="flex h-40 items-center justify-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Loading your mail map…
              </div>
            )}
            {treeError && <p className="p-6 text-sm text-destructive">{treeError}</p>}
            {tree && <MailMindmap data={tree} />}
          </CardContent>
        </Card>
      )}

      <div className="max-w-[420px] animate-fade-up" style={{ animationDelay: "180ms" }}>
        <MailChat />
      </div>
    </div>
  )
}
