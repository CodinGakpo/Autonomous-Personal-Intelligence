import { Loader2, Mail, MailX, Map, PlugZap, RefreshCw, Activity, ArrowUpRight, Zap } from "lucide-react"
import { useState } from "react"
import { motion } from "framer-motion"

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
  const connectionPercentage = rail.appsTotal > 0 ? Math.round((rail.appsConnected / rail.appsTotal) * 100) : 0

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between mb-2">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Overview</h1>
          <p className="text-muted-foreground mt-1 text-sm">Monitor your agent's connections and activities.</p>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <motion.div whileHover={{ y: -4 }} transition={{ type: "spring", stiffness: 300 }}>
          <Card className="overflow-hidden relative h-full">
            <div className="absolute top-0 right-0 p-4 opacity-10">
              <PlugZap className="h-24 w-24" />
            </div>
            <CardHeader className="flex-row items-center justify-between space-y-0 pb-2 relative z-10">
              <CardTitle className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
                Integrations
              </CardTitle>
              <div className="h-8 w-8 rounded-full bg-primary/20 flex items-center justify-center">
                <PlugZap className="h-4 w-4 text-primary" />
              </div>
            </CardHeader>
            <CardContent className="relative z-10">
              <p className="text-4xl font-bold tracking-tighter">
                {rail.appsConnected}
                <span className="text-xl font-normal text-muted-foreground ml-1">/ {rail.appsTotal}</span>
              </p>
              <div className="mt-4 flex items-center text-sm">
                <div className="w-full bg-secondary rounded-full h-1.5 mr-2">
                  <div 
                    className="bg-primary h-1.5 rounded-full" 
                    style={{ width: `${connectionPercentage}%` }}
                  />
                </div>
                <span className="text-xs text-muted-foreground whitespace-nowrap">{connectionPercentage}% Active</span>
              </div>
              <button
                type="button"
                onClick={() => onNavigate("applications")}
                className="text-xs text-primary font-medium mt-4 flex items-center hover:underline group"
              >
                Manage apps <ArrowUpRight className="h-3 w-3 ml-1 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform" />
              </button>
            </CardContent>
          </Card>
        </motion.div>

        <motion.div whileHover={{ y: -4 }} transition={{ type: "spring", stiffness: 300 }}>
          <Card className="overflow-hidden relative h-full">
            <div className="absolute top-0 right-0 p-4 opacity-10">
              <Mail className="h-24 w-24" />
            </div>
            <CardHeader className="flex-row items-center justify-between space-y-0 pb-2 relative z-10">
              <CardTitle className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
                Mail Processed
              </CardTitle>
              <div className="h-8 w-8 rounded-full bg-emerald-500/20 flex items-center justify-center">
                <Mail className="h-4 w-4 text-emerald-500" />
              </div>
            </CardHeader>
            <CardContent className="relative z-10">
              <p className="text-4xl font-bold tracking-tighter">
                {rail.mailThreads === null ? "—" : rail.mailThreads}
              </p>
              <p className="text-sm text-muted-foreground mt-1">conversations organized</p>
              <div className="mt-4 flex items-center text-xs text-emerald-500 font-medium bg-emerald-500/10 w-fit px-2 py-1 rounded-md">
                <Activity className="h-3 w-3 mr-1" />
                Live indexing active
              </div>
            </CardContent>
          </Card>
        </motion.div>

        <motion.div whileHover={{ y: -4 }} transition={{ type: "spring", stiffness: 300 }} className="sm:col-span-2 lg:col-span-1">
           <Card className="h-full bg-gradient-to-br from-primary/10 to-transparent border-primary/20">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-primary uppercase tracking-wider flex items-center gap-2">
                <Zap className="h-4 w-4" /> Agent Status
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-3">
                <span className="relative flex h-3 w-3">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-3 w-3 bg-emerald-500"></span>
                </span>
                <span className="text-lg font-semibold text-foreground">Online & Ready</span>
              </div>
              <p className="text-sm text-muted-foreground mt-4">
                The intelligence core is active and monitoring your connected data streams in real-time.
              </p>
            </CardContent>
          </Card>
        </motion.div>
      </div>

      {rail.mailConnected === false ? (
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
          <Card className="border-dashed border-2 border-muted-foreground/20 bg-transparent shadow-none hover:bg-secondary/10 transition-colors">
            <CardContent className="flex flex-col items-center justify-center gap-4 py-16 text-center">
              <div className="h-16 w-16 rounded-full bg-secondary flex items-center justify-center text-muted-foreground mb-2">
                <MailX className="h-8 w-8" />
              </div>
              <div>
                <p className="text-lg font-semibold">Gmail connection required</p>
                <p className="mt-2 text-sm text-muted-foreground max-w-sm mx-auto">
                  Connect your Gmail account to enable mail processing, summarization, and intelligent search capabilities.
                </p>
              </div>
              <Button onClick={() => onNavigate("applications")} className="mt-2">
                Connect Gmail Now
              </Button>
            </CardContent>
          </Card>
        </motion.div>
      ) : (
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
          <MailPanel />
        </motion.div>
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
        <CardHeader className="flex-row flex-wrap items-center justify-between gap-4 border-b border-border/50 bg-secondary/20 pb-4">
          <div>
            <CardTitle className="text-lg">Mail Command Center</CardTitle>
            <p className="text-xs text-muted-foreground mt-1">Automatic sync every 4 hours.</p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <select
              value={windowMinutes}
              onChange={(e) => setWindowMinutes(Number(e.target.value))}
              className="h-9 rounded-md border border-input bg-card px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring transition-all"
            >
              {WINDOW_OPTIONS.map((opt) => (
                <option key={opt.minutes} value={opt.minutes}>
                  {opt.label}
                </option>
              ))}
            </select>
            <Button onClick={handleReload} disabled={reloading} size="sm">
              {reloading ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="mr-2 h-4 w-4" />
              )}
              {reloading ? "Syncing..." : "Sync Mail"}
            </Button>
            <Button onClick={handleShowMindmap} variant="outline" size="sm" className="bg-transparent border-primary/20 text-primary hover:bg-primary/10">
              <Map className="mr-2 h-4 w-4" />
              {showMindmap ? "Hide Map" : "View Map"}
            </Button>
          </div>
        </CardHeader>
        
        {(reloadResult || reloadError) && (
          <div className={`px-6 py-3 text-sm font-medium border-b border-border/50 ${reloadError ? 'bg-destructive/10 text-destructive' : 'bg-emerald-500/10 text-emerald-500'}`}>
            {reloadResult && <span>✓ {reloadResult}</span>}
            {reloadError && <span>! {reloadError}</span>}
          </div>
        )}
      </Card>

      {showMindmap && (
        <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}>
          <Card className="border-primary/20 shadow-[0_0_30px_rgba(79,70,229,0.1)]">
            <CardContent className="pt-6">
              {treeLoading && (
                <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                  <Loader2 className="h-8 w-8 animate-spin mb-4 text-primary" />
                  <p className="text-sm font-medium">Generating neural map...</p>
                </div>
              )}
              {treeError && (
                <div className="bg-destructive/10 text-destructive p-4 rounded-md text-sm">
                  {treeError}
                </div>
              )}
              {tree && <MailMindmap data={tree} />}
            </CardContent>
          </Card>
        </motion.div>
      )}

      <div className="max-w-[420px]">
        <MailChat />
      </div>
    </div>
  )
}
