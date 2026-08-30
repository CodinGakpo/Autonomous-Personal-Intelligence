import { ArrowRight, CalendarDays, PlugZap, UserPlus, Users } from "lucide-react"
import { useEffect, useState } from "react"

import { type HealthReport, type OnboardedPerson, getHealth, getRoster } from "@/api"
import type { View } from "@/App"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"

const PRODUCT_LABELS: Record<string, string> = {
  product_one: "Product One",
  product_two: "Product Two",
  product_three: "Product Three",
}

export function Dashboard({ onNavigate }: { onNavigate: (view: View) => void }) {
  const [health, setHealth] = useState<HealthReport | null>(null)
  const [people, setPeople] = useState<OnboardedPerson[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([getHealth(), getRoster()])
      .then(([h, r]) => {
        setHealth(h)
        setPeople(r)
      })
      .catch(() => setError("Could not load the dashboard."))
  }, [])

  if (error) return <p className="text-sm text-destructive">{error}</p>
  if (!health || !people) return <p className="text-sm text-muted-foreground">Loading…</p>

  const configured = health.integrations.filter((i) => i.status === "configured").length
  const total = health.integrations.length
  const recent = [...people].slice(-5).reverse()

  return (
    <div className="flex flex-col gap-6">
      {/* Summary stat cards */}
      <div className="grid gap-4 sm:grid-cols-3">
        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle className="text-sm font-medium text-muted-foreground">People</CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-semibold">{people.length}</p>
            <p className="text-sm text-muted-foreground">onboarded to date</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Applications
            </CardTitle>
            <PlugZap className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-semibold">
              {configured}
              <span className="text-lg text-muted-foreground"> / {total}</span>
            </p>
            <div className="mt-1 flex flex-wrap gap-1">
              {health.integrations.map((i) => (
                <Badge
                  key={i.name}
                  variant={i.status === "configured" ? "default" : "secondary"}
                  className="capitalize"
                >
                  {i.name}
                </Badge>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle className="text-sm font-medium text-muted-foreground">This week</CardTitle>
            <CalendarDays className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-semibold">WBR</p>
            <p className="text-sm text-muted-foreground">weekly report — coming soon</p>
          </CardContent>
        </Card>
      </div>

      {/* Recent onboards */}
      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <div className="flex flex-col gap-1.5">
            <CardTitle>Recent onboards</CardTitle>
            <CardDescription>The latest people added to the org.</CardDescription>
          </div>
          <Button variant="outline" size="sm" onClick={() => onNavigate("roster")}>
            View all
            <ArrowRight className="ml-1 h-4 w-4" />
          </Button>
        </CardHeader>
        <CardContent>
          {recent.length === 0 ? (
            <div className="flex flex-col items-start gap-3 py-4">
              <p className="text-sm text-muted-foreground">No one has been onboarded yet.</p>
              <Button size="sm" onClick={() => onNavigate("onboard")}>
                <UserPlus className="mr-1 h-4 w-4" />
                Onboard the first person
              </Button>
            </div>
          ) : (
            <ul className="flex flex-col divide-y">
              {recent.map((p) => (
                <li key={p.email} className="flex items-center justify-between gap-4 py-3">
                  <div className="flex flex-col gap-0.5">
                    <span className="font-medium">{p.name}</span>
                    <span className="text-sm text-muted-foreground">
                      <span className="capitalize">{p.role}</span> · {p.slack_handle}
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
      </div>
    </div>
  )
}
