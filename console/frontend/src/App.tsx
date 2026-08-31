import { useEffect, useState } from "react"

import { getHealth } from "@/api"
import { getMailStatus, getMailTree } from "@/lib/brainApi"
import { Applications } from "@/pages/Applications"
import { Home } from "@/pages/Home"
import { Profile } from "@/pages/Profile"

export type View = "home" | "profile" | "applications"

const NAV: { view: View; label: string }[] = [
  { view: "home", label: "Home" },
  { view: "profile", label: "Profile" },
  { view: "applications", label: "Connected apps" },
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
    <div className="min-h-screen">
      <div className="mx-auto max-w-3xl px-6 pt-8">
        <header className="flex flex-wrap items-center justify-between gap-4 pb-6">
          <div className="flex items-center gap-3">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary text-base font-semibold text-primary-foreground">
              A
            </span>
            <div className="flex flex-col leading-tight">
              <span className="text-base font-semibold text-foreground">Agent OS</span>
              <span className="text-sm text-muted-foreground">Ask about your mail and messages</span>
            </div>
          </div>

          <div
            className="flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1.5 text-sm"
            style={{ color: rail.mailConnected ? "#15803d" : "var(--muted-foreground)" }}
          >
            <span className="status-dot" />
            <span>{rail.mailConnected ? "Gmail connected" : "Gmail not connected"}</span>
          </div>
        </header>

        <nav className="flex gap-6 border-b border-border">
          {NAV.map((n) => (
            <button
              key={n.view}
              type="button"
              onClick={() => setView(n.view)}
              className={[
                "relative -mb-px border-b-2 px-0.5 pb-3 text-sm font-medium transition-colors",
                view === n.view
                  ? "border-primary text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground",
              ].join(" ")}
            >
              {n.label}
            </button>
          ))}
        </nav>
      </div>

      <main className="mx-auto max-w-3xl px-6 pb-16 pt-6">
        {view === "home" && <Home rail={rail} onNavigate={setView} />}
        {view === "applications" && <Applications onMailStatusChange={refresh} />}
        {view === "profile" && <Profile />}
      </main>
    </div>
  )
}
