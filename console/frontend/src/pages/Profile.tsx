// A free-form list of facts about you, stored in this browser. Mail Q&A folds these into
// its prompt as light personal context (e.g. "Timezone" so it knows how to read meeting
// times, or "Team" so it can tell which mail is relevant) — see components/MailChat.tsx.
import { Plus, Trash2, UserCircle2 } from "lucide-react"
import { useEffect, useState } from "react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  type ProfileDetail as Detail,
  loadProfileDetails as loadDetails,
  saveProfileDetails as saveDetails,
} from "@/lib/profileDetails"

export function Profile() {
  const [details, setDetails] = useState<Detail[]>([])
  const [newKey, setNewKey] = useState("")
  const [newValue, setNewValue] = useState("")

  useEffect(() => {
    setDetails(loadDetails())
  }, [])

  function update(next: Detail[]) {
    setDetails(next)
    saveDetails(next)
  }

  function addDetail() {
    const key = newKey.trim()
    const value = newValue.trim()
    if (!key || !value) return
    update([...details, { id: crypto.randomUUID(), key, value }])
    setNewKey("")
    setNewValue("")
  }

  function removeDetail(id: string) {
    update(details.filter((d) => d.id !== id))
  }

  return (
    <Card className="max-w-lg">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <UserCircle2 className="h-5 w-5 text-muted-foreground" />
          About you
        </CardTitle>
        <p className="text-sm text-muted-foreground">
          Add details you want the assistant to know when it answers your questions — your
          name, timezone, role, whatever's useful. Only saved on this device.
        </p>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {details.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            You haven't added anything yet — try "Name", "Timezone", or "Team" below.
          </p>
        ) : (
          <ul className="flex flex-col divide-y divide-border">
            {details.map((d) => (
              <li key={d.id} className="flex items-center justify-between gap-3 py-2.5">
                <div className="flex min-w-0 flex-col">
                  <span className="text-sm font-medium">{d.key}</span>
                  <span className="truncate text-sm text-muted-foreground">{d.value}</span>
                </div>
                <Button
                  size="icon"
                  variant="ghost"
                  onClick={() => removeDetail(d.id)}
                  aria-label={`Remove ${d.key}`}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </li>
            ))}
          </ul>
        )}

        <div className="flex flex-col gap-2 rounded-lg border border-dashed border-input p-3">
          <div className="flex gap-2">
            <Input
              value={newKey}
              onChange={(e) => setNewKey(e.target.value)}
              placeholder="Label (e.g. Timezone)"
              className="w-2/5"
            />
            <Input
              value={newValue}
              onChange={(e) => setNewValue(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addDetail()}
              placeholder="Detail (e.g. IST, UTC+5:30)"
            />
          </div>
          <Button
            size="sm"
            variant="outline"
            onClick={addDetail}
            disabled={!newKey.trim() || !newValue.trim()}
            className="self-start"
          >
            <Plus className="mr-1 h-4 w-4" />
            Add detail
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
