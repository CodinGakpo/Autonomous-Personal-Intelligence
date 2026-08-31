import { Mail, PlugZap, UserPlus, Users } from "lucide-react"
import { useEffect, useState } from "react"

import { type RosterEntry, getRoster } from "@/api"
import type { View } from "@/App"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

const PRODUCT_LABELS: Record<string, string> = {
  product_one: "Product One",
  product_two: "Product Two",
  product_three: "Product Three",
}

interface DashboardRail {
  people: number
  appsConnected: number
  appsTotal: number
  mailThreads: number | null
}

export function Dashboard({
  onNavigate,
  rail,
}: {
  onNavigate: (view: View) => void
  rail: DashboardRail
}) {
  const [people, setPeople] = useState<RosterEntry[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getRoster()
      .then(setPeople)
      .catch(() => setError("Could not load the team list."))
  }, [])

  const recent = people ? [...people].slice(-5).reverse() : []

  return (
    <div className="flex flex-col gap-6">
      {/* Summary readouts */}
      <div className="grid gap-4 sm:grid-cols-3">
        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="font-readout text-[11px] font-normal uppercase tracking-widest text-muted-foreground">
              People
            </CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <p className="font-readout text-3xl font-bold tabular-nums">{rail.people}</p>
            <p className="text-sm text-muted-foreground">onboarded so far</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="font-readout text-[11px] font-normal uppercase tracking-widest text-muted-foreground">
              Applications
            </CardTitle>
            <PlugZap className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <p className="font-readout text-3xl font-bold tabular-nums">
              {rail.appsConnected}
              <span className="text-lg text-muted-foreground"> / {rail.appsTotal}</span>
            </p>
            <p className="text-sm text-muted-foreground">connected — Gmail is live</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="font-readout text-[11px] font-normal uppercase tracking-widest text-muted-foreground">
              Mail tree
            </CardTitle>
            <Mail className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <p className="font-readout text-3xl font-bold tabular-nums">
              {rail.mailThreads === null ? "—" : rail.mailThreads}
            </p>
            <p className="text-sm text-muted-foreground">threads ingested</p>
          </CardContent>
        </Card>
      </div>

      {/* Team preview */}
      <Card>
        <CardHeader>
          <CardTitle>Team</CardTitle>
          <p className="text-sm text-muted-foreground">The most recently onboarded people.</p>
        </CardHeader>
        <CardContent>
          {error && <p className="text-sm text-destructive">{error}</p>}
          {!error && people === null && (
            <p className="text-sm text-muted-foreground">Loading…</p>
          )}
          {!error && people !== null && recent.length === 0 && (
            <div className="flex flex-col items-start gap-3 py-4">
              <p className="text-sm text-muted-foreground">
                No one has been onboarded yet — this is where your team will show up.
              </p>
              <Button size="sm" onClick={() => onNavigate("onboard")}>
                <UserPlus className="mr-1 h-4 w-4" />
                Onboard the first person
              </Button>
            </div>
          )}
          {recent.length > 0 && (
            <ul className="flex flex-col divide-y divide-border">
              {recent.map((p) => (
                <li key={p.email ?? p.name} className="flex items-center justify-between gap-4 py-3">
                  <div className="flex flex-col gap-0.5">
                    <span className="font-medium">{p.name}</span>
                    <span className="text-sm text-muted-foreground">
                      <span className="capitalize">{p.role.replace("_", " ")}</span> · @{p.slack_handle}
                    </span>
                  </div>
                  <div className="flex flex-wrap items-center justify-end gap-1">
                    {p.products.map((prod) => (
                      <Badge key={prod} variant="outline">
                        {PRODUCT_LABELS[prod] ?? prod}
                      </Badge>
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {/* Quick actions */}
      <div className="flex flex-wrap gap-3">
        <Button onClick={() => onNavigate("onboard")}>
          <UserPlus className="mr-1 h-4 w-4" />
          Onboard a person
        </Button>
        <Button variant="outline" onClick={() => onNavigate("applications")}>
          Manage applications
        </Button>
        <Button variant="outline" onClick={() => onNavigate("mail")}>
          Open mail tree
        </Button>
      </div>
    </div>
  )
}
