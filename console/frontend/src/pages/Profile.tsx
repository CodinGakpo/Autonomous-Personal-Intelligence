import { UserCircle2 } from "lucide-react"
import { useEffect, useState } from "react"

import { ApiError, type RosterEntry, getMyProfile } from "@/api"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

type LoadState = "loading" | "empty" | "error" | "ready"

export function Profile() {
  const [profile, setProfile] = useState<RosterEntry | null>(null)
  const [state, setState] = useState<LoadState>("loading")

  useEffect(() => {
    getMyProfile()
      .then((p) => {
        setProfile(p)
        setState("ready")
      })
      .catch((e: unknown) => {
        // No signed-in identity is matched to a roster entry yet — expected until
        // onboarding + sign-in are connected, not a failure worth alarming over.
        setState(e instanceof ApiError && e.status === 404 ? "empty" : "error")
      })
  }, [])

  if (state === "loading") {
    return <p className="text-sm text-muted-foreground">Loading profile…</p>
  }

  if (state === "empty") {
    return (
      <Card className="max-w-lg">
        <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
          <UserCircle2 className="h-10 w-10 text-muted-foreground" />
          <div>
            <p className="font-medium">No profile yet</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Your profile appears here once you're onboarded and signed in.
            </p>
          </div>
        </CardContent>
      </Card>
    )
  }

  if (state === "error" || !profile) {
    return (
      <p className="text-sm text-destructive">
        Couldn't load your profile — try again in a moment.
      </p>
    )
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
            <span className="font-readout text-xs uppercase tracking-widest text-muted-foreground">
              Email
            </span>
            <span>{profile.email}</span>
          </div>
        )}
        <div className="flex flex-col gap-0.5">
          <span className="font-readout text-xs uppercase tracking-widest text-muted-foreground">
            Slack
          </span>
          <span>@{profile.slack_handle}</span>
        </div>
        {profile.products.length > 0 && (
          <div className="flex flex-col gap-1.5">
            <span className="font-readout text-xs uppercase tracking-widest text-muted-foreground">
              Products
            </span>
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
            <span className="font-readout text-xs uppercase tracking-widest text-muted-foreground">
              ClickUp
            </span>
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
