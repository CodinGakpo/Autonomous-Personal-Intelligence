import { useEffect, useState } from "react"

import { type RosterEntry, getRoster } from "@/api"
import { isPrivileged } from "@/auth"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

interface RosterProps {
  refreshKey: number
  onViewProfile?: (email: string) => void
}

export function Roster({ refreshKey, onViewProfile }: RosterProps) {
  const [people, setPeople] = useState<RosterEntry[]>([])
  const privileged = isPrivileged()

  useEffect(() => {
    getRoster()
      .then(setPeople)
      .catch(() => setPeople([]))
  }, [refreshKey])

  if (people.length === 0)
    return <p className="text-sm text-muted-foreground">No one onboarded yet.</p>

  return (
    <div className="space-y-2">
      {!privileged && (
        <p className="text-xs text-muted-foreground">
          ℹ️ Email addresses and ClickUp links are visible to admins and team leads only.
        </p>
      )}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>Role</TableHead>
            <TableHead>Slack</TableHead>
            <TableHead>Products</TableHead>
            {privileged && <TableHead>Email</TableHead>}
            {privileged && <TableHead>ClickUp</TableHead>}
            <TableHead></TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {people.map((p, idx) => (
            <TableRow
              key={idx}
              className={p.is_own ? "bg-primary/5 font-medium" : undefined}
            >
              <TableCell className="font-medium">
                {p.name}
                {p.is_own && (
                  <Badge variant="secondary" className="ml-2 text-[10px]">
                    you
                  </Badge>
                )}
              </TableCell>
              <TableCell className="capitalize">{p.role.replace("_", " ")}</TableCell>
              <TableCell>{p.slack_handle}</TableCell>
              <TableCell>
                <div className="flex flex-wrap gap-1">
                  {p.products.map((prod) => (
                    <Badge key={prod} variant="outline" className="text-[10px]">
                      {prod.replace("_", " ")}
                    </Badge>
                  ))}
                </div>
              </TableCell>
              {privileged && (
                <TableCell className="text-muted-foreground text-sm">
                  {p.email ?? "—"}
                </TableCell>
              )}
              {privileged && (
                <TableCell>
                  {p.clickup_url ? (
                    <a
                      href={p.clickup_url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-primary underline-offset-4 hover:underline"
                    >
                      open
                    </a>
                  ) : (
                    "—"
                  )}
                </TableCell>
              )}
              <TableCell>
                {(p.is_own || privileged) && p.email && onViewProfile && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => onViewProfile(p.email!)}
                    className="text-xs"
                  >
                    Profile →
                  </Button>
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
