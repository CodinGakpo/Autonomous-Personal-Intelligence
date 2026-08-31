import { Loader2, MailX, Network, RefreshCw } from "lucide-react"
import { useState } from "react"

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

export function MailTree({ mailConnected }: { mailConnected: boolean | null }) {
  if (mailConnected === false) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
          <MailX className="h-10 w-10 text-muted-foreground" />
          <div>
            <p className="font-medium">Gmail isn't connected</p>
            <p className="mt-1 text-sm text-muted-foreground">
              The mail tree, reload, and chat are hidden until Gmail is reconnected from the
              Applications tab.
            </p>
          </div>
        </CardContent>
      </Card>
    )
  }

  return <MailTreeContent />
}

function MailTreeContent() {
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
      setReloadResult(`Processed ${result.processed} email${result.processed === 1 ? "" : "s"}.`)
      if (showMindmap) {
        const updated = await getMailTree()
        setTree(updated)
      }
    } catch (err) {
      setReloadError(err instanceof Error ? err.message : "Reload failed.")
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
      setTreeError(err instanceof Error ? err.message : "Could not load the mail tree.")
    } finally {
      setTreeLoading(false)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader className="flex-row flex-wrap items-center justify-between gap-3">
          <CardTitle>Mail Tree</CardTitle>
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
              Reload
            </Button>
            <Button onClick={handleShowMindmap} variant="outline" size="sm">
              <Network className="mr-1 h-4 w-4" />
              {showMindmap ? "Hide mindmap" : "Show mindmap"}
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            A background job also runs every 4 hours automatically. Use Reload to catch up sooner.
          </p>
          {reloadResult && <p className="mt-2 text-sm text-primary">{reloadResult}</p>}
          {reloadError && <p className="mt-2 text-sm text-destructive">{reloadError}</p>}
        </CardContent>
      </Card>

      {showMindmap && (
        <Card>
          <CardContent className="pt-6">
            {treeLoading && <p className="text-sm text-muted-foreground">Loading mail tree…</p>}
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
