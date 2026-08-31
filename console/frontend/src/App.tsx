import { useEffect, useState } from "react"

import { getHealth, getRoster } from "@/api"
import { getMailStatus, getMailTree } from "@/lib/brainApi"
import { Applications } from "@/pages/Applications"
import { Dashboard } from "@/pages/Dashboard"
import { MailTree } from "@/pages/MailTree"
import { Onboard } from "@/pages/Onboard"
import { Profile } from "@/pages/Profile"

export type View = "dashboard" | "applications" | "onboard" | "profile" | "mail"

const NAV: { view: View; label: string }[] = [
  { view: "dashboard", label: "Dashboard" },
  { view: "onboard", label: "Onboard" },
  { view: "profile", label: "Profile" },
  { view: "applications", label: "Applications" },
  { view: "mail", label: "Mail tree" },
]

interface Rail {
  people: number
  appsConnected: number
  appsTotal: number
  mailThreads: number | null
  mailConnected: boolean | null
}

export default function App() {
  const [view, setView] = useState<View>("dashboard")
  const [refreshKey, setRefreshKey] = useState(0)
  const [rail, setRail] = useState<Rail>({
    people: 0,
    appsConnected: 0,
    appsTotal: 0,
    mailThreads: null,
    mailConnected: null,
  })

  useEffect(() => {
    let cancelled = false

    Promise.all([getRoster(), getHealth(), getMailStatus().catch(() => ({ connected: false }))]).then(
      ([roster, health, mail]) => {
        if (cancelled) return
        const connected = health.integrations.filter((i) => i.status === "configured").length
        setRail((r) => ({
          ...r,
          people: roster.length,
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
  const systemsNominal = rail.appsConnected > 0

  return (
    <div className="min-h-screen">
      <div className="mx-auto max-w-5xl px-6 pt-6">
        <header className="flex flex-wrap items-center justify-between gap-4 pb-4">
          <div className="flex items-center gap-3">
            <span className="flex h-8 w-8 items-center justify-center rounded-md bg-primary font-readout text-sm font-bold text-primary-foreground">
              A
            </span>
            <div className="flex flex-col leading-none">
              <span className="font-readout text-sm font-bold tracking-[0.15em] text-foreground">
                AGENT_OS
              </span>
              <span className="mt-0.5 font-readout text-[10px] tracking-[0.2em] text-muted-foreground">
                OPS CONSOLE
              </span>
            </div>
          </div>

          <div
            className="flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1.5 font-readout text-[11px] tracking-wide"
            style={{ color: systemsNominal ? "var(--primary)" : "var(--caution)" }}
          >
            <span className="status-dot status-dot-live" />
            <span>{systemsNominal ? "SYSTEMS NOMINAL" : "AWAITING SETUP"}</span>
          </div>
        </header>

        <nav className="flex gap-5 border-b border-border">
          {NAV.map((n) => (
            <button
              key={n.view}
              type="button"
              onClick={() => setView(n.view)}
              className={[
                "relative -mb-px border-b-2 px-0.5 pb-3 font-readout text-[11px] tracking-[0.12em] uppercase transition-colors",
                view === n.view
                  ? "border-primary text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground",
              ].join(" ")}
            >
              {n.label}
            </button>
          ))}
        </nav>

        <div className="flex flex-wrap gap-x-6 gap-y-1 py-3 font-readout text-[11px] text-muted-foreground">
          <span>
            PEOPLE <b className="text-foreground">{String(rail.people).padStart(2, "0")}</b>
          </span>
          <span>
            APPS{" "}
            <b className="text-foreground">
              {rail.appsConnected}/{rail.appsTotal}
            </b>
          </span>
          <span>
            MAIL THREADS{" "}
            <b className="text-foreground">{rail.mailThreads === null ? "—" : rail.mailThreads}</b>
          </span>
        </div>
      </div>

      <main className="mx-auto max-w-5xl px-6 pb-16 pt-4">
        {view === "dashboard" && <Dashboard onNavigate={setView} rail={rail} />}
        {view === "applications" && <Applications onMailStatusChange={refresh} />}
        {view === "onboard" && <Onboard onDone={refresh} />}
        {view === "profile" && <Profile />}
        {view === "mail" && <MailTree mailConnected={rail.mailConnected} />}
      </main>
    </div>
  )
}
