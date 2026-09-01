import { PlugZap, Sparkles, UserCircle2 } from "lucide-react"
import { useEffect, useState } from "react"

import { getHealth } from "@/api"
import { getMailStatus, getMailTree } from "@/lib/brainApi"
import { Applications } from "@/pages/Applications"
import { Home } from "@/pages/Home"
import { Profile } from "@/pages/Profile"

export type View = "home" | "profile" | "applications"

const NAV: { view: View; label: string; icon: typeof Sparkles }[] = [
  { view: "home", label: "Home", icon: Sparkles },
  { view: "profile", label: "Profile", icon: UserCircle2 },
  { view: "applications", label: "Connected apps", icon: PlugZap },
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
  const [scrolled, setScrolled] = useState(false)
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

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 4)
    onScroll()
    window.addEventListener("scroll", onScroll, { passive: true })
    return () => window.removeEventListener("scroll", onScroll)
  }, [])

  const refresh = () => setRefreshKey((k) => k + 1)

  return (
    <div className="min-h-screen">
      <div
        className={[
          "sticky top-0 z-20 border-b backdrop-blur-md transition-shadow duration-300",
          scrolled ? "border-border bg-background/80 shadow-elev-sm" : "border-transparent bg-background/40",
        ].join(" ")}
      >
        <div className="mx-auto max-w-3xl px-6 pt-6">
          <header className="flex flex-wrap items-center justify-between gap-4 pb-5">
            <div className="flex items-center gap-3">
              <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-gradient-to-br from-primary to-indigo-500 text-base font-semibold text-primary-foreground shadow-glow">
                A
              </span>
              <div className="flex flex-col leading-tight">
                <span className="text-base font-semibold tracking-tight text-foreground">Agent OS</span>
                <span className="text-sm text-muted-foreground">Ask about your mail and messages</span>
              </div>
            </div>

            <div
              className="flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1.5 text-sm shadow-elev-sm"
              style={{ color: rail.mailConnected ? "#15803d" : "var(--muted-foreground)" }}
            >
              <span className={rail.mailConnected ? "status-dot status-dot-live" : "status-dot"} />
              <span>{rail.mailConnected ? "Gmail connected" : "Gmail not connected"}</span>
            </div>
          </header>

          <nav className="flex gap-1">
            {NAV.map((n) => {
              const Icon = n.icon
              const active = view === n.view
              return (
                <button
                  key={n.view}
                  type="button"
                  onClick={() => setView(n.view)}
                  className={[
                    "relative flex items-center gap-1.5 rounded-t-lg px-3.5 pb-3 pt-2 text-sm font-medium transition-colors",
                    active ? "text-foreground" : "text-muted-foreground hover:text-foreground",
                  ].join(" ")}
                >
                  <Icon className={["h-4 w-4 transition-colors", active ? "text-primary" : "text-muted-foreground/70"].join(" ")} />
                  {n.label}
                  <span
                    className={[
                      "absolute inset-x-2 bottom-0 h-0.5 rounded-full bg-primary transition-all duration-300 ease-out",
                      active ? "opacity-100 scale-x-100" : "opacity-0 scale-x-0",
                    ].join(" ")}
                  />
                </button>
              )
            })}
          </nav>
        </div>
      </div>

      <main className="mx-auto max-w-3xl px-6 pb-16 pt-8">
        <div key={view} className="animate-fade-up">
          {view === "home" && <Home rail={rail} onNavigate={setView} />}
          {view === "applications" && <Applications onMailStatusChange={refresh} />}
          {view === "profile" && <Profile />}
        </div>
      </main>
    </div>
  )
}
