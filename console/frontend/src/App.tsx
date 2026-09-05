import { useEffect, useState } from "react"
import { LayoutDashboard, User, Plug, CheckCircle2, XCircle } from "lucide-react"
import { motion, AnimatePresence } from "framer-motion"

import { getHealth } from "@/api"
import { getMailStatus, getMailTree } from "@/lib/brainApi"
import { Applications } from "@/pages/Applications"
import { Home } from "@/pages/Home"
import { Profile } from "@/pages/Profile"
import { ThemeToggle } from "@/components/ThemeToggle"

export type View = "home" | "profile" | "applications"

const NAV = [
  { view: "home" as View, label: "Dashboard", icon: LayoutDashboard },
  { view: "applications" as View, label: "Integrations", icon: Plug },
  { view: "profile" as View, label: "Profile", icon: User },
]

interface Rail {
  appsConnected: number
  appsTotal: number
  mailThreads: number | null
  mailConnected: boolean | null
}

export default function App() {
  const [view, setView] = useState<View>("home")
  const [refreshKey, setRefreshKey] = useState(0)
  const [rail, setRail] = useState<Rail>({
    appsConnected: 0,
    appsTotal: 0,
    mailThreads: null,
    mailConnected: null,
  })

  useEffect(() => {
    let cancelled = false

    Promise.all([getHealth(), getMailStatus().catch(() => ({ connected: false }))]).then(
      ([health, mail]) => {
        if (cancelled) return
        const connected = health.integrations.filter((i) => i.status === "configured").length
        setRail((r) => ({
          ...r,
          appsConnected: connected + (mail.connected ? 1 : 0),
          appsTotal: health.integrations.length + 1,
          mailConnected: mail.connected,
        }))
      },
    )

    getMailTree()
      .then((tree) => {
        if (cancelled) return
        let threads = 0
        const walk = (n: typeof tree) => {
          if (n.type === "mail_thread") threads++
          ;(n.children || []).forEach(walk)
        }
        walk(tree)
        setRail((r) => ({ ...r, mailThreads: threads }))
      })
      .catch(() => {
        if (!cancelled) setRail((r) => ({ ...r, mailThreads: null }))
      })

    return () => {
      cancelled = true
    }
  }, [refreshKey])

  const refresh = () => setRefreshKey((k) => k + 1)

  return (
    <div className="flex min-h-screen bg-background text-foreground selection:bg-primary/30">
      {/* Sidebar Navigation */}
      <aside className="w-64 border-r border-border bg-card flex-col hidden md:flex z-10 shadow-xl shadow-black/10">
        <div className="h-16 flex items-center px-6 border-b border-border/50">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-sm font-bold text-primary-foreground shadow-[0_0_15px_rgba(79,70,229,0.5)]">
              A
            </div>
            <span className="text-sm font-semibold tracking-wide">Agent OS</span>
          </div>
        </div>
        
        <nav className="flex-1 px-4 py-6 space-y-1">
          {NAV.map((n) => {
            const Icon = n.icon
            const active = view === n.view
            return (
              <button
                key={n.view}
                type="button"
                onClick={() => setView(n.view)}
                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 ${
                  active 
                    ? "bg-primary/10 text-primary" 
                    : "text-muted-foreground hover:bg-secondary/50 hover:text-foreground"
                }`}
              >
                <Icon className={`h-4 w-4 ${active ? "text-primary" : "opacity-70"}`} />
                {n.label}
              </button>
            )
          })}
        </nav>

        <div className="p-4 border-t border-border/50">
          <div className="flex items-center justify-between text-[11px] uppercase tracking-wider font-semibold text-muted-foreground mb-3 px-2">
            <span>System Status</span>
            <ThemeToggle />
          </div>
          <div className="flex items-center gap-3 rounded-lg bg-secondary/30 px-3 py-2.5 border border-border/30">
            {rail.mailConnected ? (
              <CheckCircle2 className="h-4 w-4 text-emerald-500" />
            ) : (
              <XCircle className="h-4 w-4 text-muted-foreground" />
            )}
            <span className="text-xs font-medium text-secondary-foreground">
              {rail.mailConnected ? "Gmail Connected" : "Gmail Disconnected"}
            </span>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 flex flex-col h-screen overflow-hidden bg-background">
        {/* Mobile Header */}
        <header className="h-16 md:hidden flex items-center justify-between px-6 border-b border-border bg-card">
           <div className="flex items-center gap-3">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-sm font-bold text-primary-foreground shadow-lg shadow-primary/20">
              A
            </span>
            <span className="text-sm font-semibold">Agent OS</span>
          </div>
          <div className="flex items-center gap-2">
            <select 
              value={view} 
              onChange={(e) => setView(e.target.value as View)}
              className="text-sm bg-transparent border-none outline-none font-medium"
            >
              {NAV.map(n => <option key={n.view} value={n.view}>{n.label}</option>)}
            </select>
            <ThemeToggle />
          </div>
        </header>

        {/* Scrollable Page Content */}
        <div className="flex-1 overflow-auto p-6 md:p-10 relative">
          {/* Subtle background glow effect */}
          <div className="pointer-events-none absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[400px] bg-primary/5 rounded-full blur-3xl opacity-50" />
          
          <div className="max-w-4xl mx-auto w-full relative z-10">
            <AnimatePresence mode="wait">
              <motion.div
                key={view}
                initial={{ opacity: 0, y: 15, filter: "blur(4px)" }}
                animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
                exit={{ opacity: 0, y: -15, filter: "blur(4px)" }}
                transition={{ duration: 0.25, ease: "easeOut" }}
              >
                {view === "home" && <Home rail={rail} onNavigate={setView} />}
                {view === "applications" && <Applications onMailStatusChange={refresh} />}
                {view === "profile" && <Profile />}
              </motion.div>
            </AnimatePresence>
          </div>
        </div>
      </main>
    </div>
  )
}
