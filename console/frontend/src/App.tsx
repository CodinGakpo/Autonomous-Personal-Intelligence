import { useState } from "react"

import { Button } from "@/components/ui/button"
import { Applications } from "@/pages/Applications"
import { Dashboard } from "@/pages/Dashboard"
import { HrTools } from "@/pages/HrTools"
import { Onboard } from "@/pages/Onboard"
import { Profile } from "@/pages/Profile"
import { Roster } from "@/pages/Roster"

export type View = "dashboard" | "applications" | "onboard" | "roster" | "profile" | "hr-tools"

export default function App() {
  const [view, setView] = useState<View>("dashboard")
  const [rosterKey, setRosterKey] = useState(0)

  // Demo mode: always admin, no login required.
  const NAV: { view: View; label: string }[] = [
    { view: "dashboard",    label: "Dashboard" },
    { view: "roster",       label: "Roster" },
    { view: "profile",      label: "Profile" },
    { view: "onboard",      label: "Onboard" },
    { view: "hr-tools",     label: "HR Tools" },
    { view: "applications", label: "Applications" },
  ]

  return (
    <div className="mx-auto max-w-5xl p-6">
      <header className="mb-6 flex items-center justify-between border-b pb-4">
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-2.5">
            <span className="flex h-7 w-7 items-center justify-center rounded-md bg-primary font-mono text-sm font-bold text-primary-foreground">
              A
            </span>
            <h1 className="font-semibold tracking-tight">
              Agent OS{" "}
              <span className="font-normal text-muted-foreground">Ops Console</span>
            </h1>
          </div>
          <nav className="ml-6 flex gap-1">
            {NAV.map((n) => (
              <Button
                key={n.view}
                variant={view === n.view ? "secondary" : "ghost"}
                size="sm"
                onClick={() => setView(n.view)}
              >
                {n.label}
              </Button>
            ))}
          </nav>
        </div>
        <span className="rounded-full bg-muted px-2.5 py-0.5 text-xs font-medium text-muted-foreground">
          demo · admin
        </span>
      </header>

      <main>
        {view === "dashboard"    && <Dashboard onNavigate={setView} />}
        {view === "applications" && <Applications />}
        {view === "onboard"      && <Onboard onDone={() => setRosterKey((k) => k + 1)} />}
        {view === "roster"       && <Roster refreshKey={rosterKey} onViewProfile={() => setView("profile")} />}
        {view === "profile"      && <Profile />}
        {view === "hr-tools"     && <HrTools />}
      </main>
    </div>
  )
}
