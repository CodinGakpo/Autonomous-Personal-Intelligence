import { useEffect, useState } from "react"

import { type RosterEntry, getMyProfile } from "@/api"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

export function Profile() {
  const [profile, setProfile] = useState<RosterEntry | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getMyProfile()
      .then(setProfile)
      .catch((e: Error) => setError(e.message))
  }, [])

  if (error) {
    return <p className="text-sm text-destructive">{error}</p>
  }

  if (!profile) {
    return <p className="text-sm text-muted-foreground">Loading profile…</p>
  }

  return (
    <Card className="max-w-lg">
      <CardHeader>
        <CardTitle>{profile.name}</CardTitle>
        <p className="text-sm text-muted-foreground capitalize">{profile.role.replace("_", " ")}</p>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 text-sm">
        {profile.email && (
          <div className="flex flex-col gap-0.5">
            <span className="text-xs text-muted-foreground uppercase tracking-wide">Email</span>
            <span>{profile.email}</span>
          </div>
        )}
        <div className="flex flex-col gap-0.5">
          <span className="text-xs text-muted-foreground uppercase tracking-wide">Slack</span>
          <span>@{profile.slack_handle}</span>
        </div>
        {profile.products.length > 0 && (
          <div className="flex flex-col gap-1.5">
            <span className="text-xs text-muted-foreground uppercase tracking-wide">Products</span>
            <div className="flex flex-wrap gap-1">
              {profile.products.map((p) => (
                <Badge key={p} variant="outline" className="text-[10px]">
                  {p.replace("_", " ")}
                </Badge>
              ))}
            </div>
          </div>
        )}
        {profile.clickup_url && (
          <div className="flex flex-col gap-0.5">
            <span className="text-xs text-muted-foreground uppercase tracking-wide">ClickUp</span>
            <a
              href={profile.clickup_url}
              target="_blank"
              rel="noreferrer"
              className="text-primary underline-offset-4 hover:underline"
            >
              Open task ↗
            </a>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
