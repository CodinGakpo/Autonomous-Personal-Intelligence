/**
 * HrTools — dedicated HR operations page.
 *
 * Tab 1 · Resumes  : upload a résumé file for a specific employee.
 * Tab 2 · Slack ID : assign or update the Slack handle for an existing
 *                    roster member (populated from GET /roster).
 *
 * NOTE: The résumé upload and Slack handle PATCH are frontend stubs only.
 * See `api.ts` for the BACKEND TODO comments that describe each endpoint.
 */

import { FileText, Slack, Upload, X } from "lucide-react"
import { type ChangeEvent, type FormEvent, useEffect, useRef, useState } from "react"

import {
  type RosterEntry,
  type UpdateSlackHandleRequest,
  getRoster,
  updateSlackHandle,
} from "@/api"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

type Tab = "resumes" | "slack"

// Resume upload constraints (client-side validation mirrors Onboard.tsx).
const RESUME_ACCEPT = ".pdf,.doc,.docx"
const RESUME_MAX_BYTES = 5 * 1024 * 1024 // 5 MB
const RESUME_EXTS = ["pdf", "doc", "docx"]

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

// ---------------------------------------------------------------------------
// TabButton — styled tab pill (matches the rest of the console's ghost/secondary pattern)
// ---------------------------------------------------------------------------

function TabButton({
  active,
  icon,
  label,
  onClick,
}: {
  active: boolean
  icon: React.ReactNode
  label: string
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        "inline-flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-colors",
        active
          ? "bg-secondary text-secondary-foreground shadow-sm"
          : "text-muted-foreground hover:bg-secondary/60 hover:text-foreground",
      ].join(" ")}
    >
      {icon}
      {label}
    </button>
  )
}

// ---------------------------------------------------------------------------
// ResumeTab
// ---------------------------------------------------------------------------

function ResumeTab({ roster }: { roster: RosterEntry[] }) {
  const [selectedEmail, setSelectedEmail] = useState("")
  const [resume, setResume] = useState<File | null>(null)
  const [resumeError, setResumeError] = useState<string | null>(null)
  const [message, setMessage] = useState<{ text: string; ok: boolean } | null>(null)
  const [busy, setBusy] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  function onPickResume(e: ChangeEvent<HTMLInputElement>) {
    setResumeError(null)
    const file = e.target.files?.[0]
    if (!file) return
    const ext = file.name.split(".").pop()?.toLowerCase() ?? ""
    if (!RESUME_EXTS.includes(ext)) {
      setResumeError("Resume must be a PDF, DOC, or DOCX file.")
      return
    }
    if (file.size > RESUME_MAX_BYTES) {
      setResumeError("Resume is larger than 5 MB.")
      return
    }
    setResume(file)
  }

  function clearResume() {
    setResume(null)
    setResumeError(null)
    if (fileRef.current) fileRef.current.value = ""
  }

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!selectedEmail) return
    setBusy(true)
    setMessage(null)

    try {
      // NOTE: A multipart upload endpoint (POST /resume/upload) is needed on
      // the backend to persist this file. Once that endpoint exists, send
      // `resume` as FormData alongside `selectedEmail`. For now we just
      // simulate a successful submission.
      // BACKEND TODO: implement POST /resume/upload (multipart/form-data:
      //   email: string, file: UploadFile) → store in _samples/resume_{slug}.json
      await new Promise((r) => setTimeout(r, 600)) // simulated latency
      const employee = roster.find((p) => p.email === selectedEmail)
      setMessage({
        text: `Resume "${resume?.name}" attached to ${employee?.name ?? selectedEmail}. (Pending backend endpoint.)`,
        ok: true,
      })
      setSelectedEmail("")
      clearResume()
    } catch {
      setMessage({ text: "Upload failed — please try again.", ok: false })
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card className="max-w-lg">
      <CardHeader>
        <CardTitle>Upload a résumé</CardTitle>
        <p className="text-sm text-muted-foreground">
          Attach a résumé file to an existing team member's profile.
        </p>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="flex flex-col gap-4">
          {/* Employee selector */}
          <div className="flex flex-col gap-2">
            <Label htmlFor="resume-employee">Employee</Label>
            <select
              id="resume-employee"
              value={selectedEmail}
              onChange={(e) => setSelectedEmail(e.target.value)}
              required
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            >
              <option value="" disabled>
                {roster.length === 0 ? "Loading employees…" : "Select an employee"}
              </option>
              {roster.map((p) => (
                <option key={p.email ?? p.name} value={p.email ?? ""}>
                  {p.name}
                  {p.email ? ` — ${p.email}` : ""}
                </option>
              ))}
            </select>
          </div>

          {/* File picker */}
          <div className="flex flex-col gap-2">
            <Label htmlFor="resume-file">Résumé file</Label>
            <input
              ref={fileRef}
              id="resume-file"
              type="file"
              accept={RESUME_ACCEPT}
              onChange={onPickResume}
              className="hidden"
            />
            {resume ? (
              <div className="flex items-center justify-between gap-3 rounded-md border border-input bg-secondary/40 px-3 py-2">
                <div className="flex min-w-0 items-center gap-2">
                  <FileText className="h-4 w-4 shrink-0 text-primary" />
                  <span className="truncate text-sm">{resume.name}</span>
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {formatSize(resume.size)}
                  </span>
                </div>
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  onClick={clearResume}
                  aria-label="Remove résumé"
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => fileRef.current?.click()}
                className="flex w-full flex-col items-center justify-center gap-1 rounded-md border border-dashed border-input bg-transparent px-3 py-6 text-sm text-muted-foreground transition-colors hover:border-ring hover:text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              >
                <Upload className="h-5 w-5" />
                <span>
                  Click to upload <span className="text-foreground">résumé</span>
                </span>
                <span className="text-xs">PDF, DOC, or DOCX · up to 5 MB</span>
              </button>
            )}
            {resumeError && <p className="text-sm text-destructive">{resumeError}</p>}
          </div>

          {message && (
            <p className={`text-sm ${message.ok ? "text-muted-foreground" : "text-destructive"}`}>
              {message.text}
            </p>
          )}

          <Button type="submit" disabled={busy || !resume || !selectedEmail}>
            {busy ? "Uploading…" : "Upload résumé"}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// SlackTab
// ---------------------------------------------------------------------------

function SlackTab({ roster }: { roster: RosterEntry[] }) {
  const [selectedEmail, setSelectedEmail] = useState("")
  const [slackHandle, setSlackHandle] = useState("")
  const [message, setMessage] = useState<{ text: string; ok: boolean } | null>(null)
  const [busy, setBusy] = useState(false)

  // Pre-fill the handle when the user picks an employee.
  function onSelectEmployee(email: string) {
    setSelectedEmail(email)
    setMessage(null)
    const match = roster.find((p) => p.email === email)
    setSlackHandle(match?.slack_handle ?? "")
  }

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!selectedEmail || !slackHandle.trim()) return
    setBusy(true)
    setMessage(null)

    const body: UpdateSlackHandleRequest = {
      slack_handle: slackHandle.trim().replace(/^@/, ""), // strip leading @ if user types it
    }

    try {
      // BACKEND TODO: implement PATCH /roster/{email}/slack (see api.ts for the
      // full spec). Until the endpoint exists this call will 404; the backend
      // dev should wire it up per the spec in api.ts.
      await updateSlackHandle(selectedEmail, body)
      const employee = roster.find((p) => p.email === selectedEmail)
      setMessage({
        text: `Slack handle updated to @${body.slack_handle} for ${employee?.name ?? selectedEmail}.`,
        ok: true,
      })
      setSelectedEmail("")
      setSlackHandle("")
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Unknown error"
      setMessage({ text: `Update failed: ${msg}`, ok: false })
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card className="max-w-lg">
      <CardHeader>
        <CardTitle>Assign Slack handle</CardTitle>
        <p className="text-sm text-muted-foreground">
          Select a team member and update their Slack handle. The Hermes agent uses this to
          route messages to the right person.
        </p>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="flex flex-col gap-4">
          {/* Employee selector */}
          <div className="flex flex-col gap-2">
            <Label htmlFor="slack-employee">Employee</Label>
            <select
              id="slack-employee"
              value={selectedEmail}
              onChange={(e) => onSelectEmployee(e.target.value)}
              required
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            >
              <option value="" disabled>
                {roster.length === 0 ? "Loading employees…" : "Select an employee"}
              </option>
              {roster.map((p) => (
                <option key={p.email ?? p.name} value={p.email ?? ""}>
                  {p.name}
                  {p.email ? ` — ${p.email}` : ""}
                </option>
              ))}
            </select>
          </div>

          {/* Slack handle input */}
          <div className="flex flex-col gap-2">
            <Label htmlFor="slack-handle">Slack handle</Label>
            <div className="relative">
              <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-muted-foreground text-sm select-none">
                @
              </span>
              <Input
                id="slack-handle"
                value={slackHandle.replace(/^@/, "")}
                onChange={(e) => setSlackHandle(e.target.value)}
                placeholder="username"
                className="pl-7"
                required
              />
            </div>
            <p className="text-xs text-muted-foreground">
              Enter the Slack username without the @ prefix (e.g.{" "}
              <span className="font-mono">john.doe</span>).
            </p>
          </div>

          {message && (
            <p className={`text-sm ${message.ok ? "text-muted-foreground" : "text-destructive"}`}>
              {message.text}
            </p>
          )}

          <Button type="submit" disabled={busy || !selectedEmail || !slackHandle.trim()}>
            {busy ? "Saving…" : "Save Slack handle"}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// HrTools (exported page component)
// ---------------------------------------------------------------------------

export function HrTools() {
  const [tab, setTab] = useState<Tab>("resumes")
  const [roster, setRoster] = useState<RosterEntry[]>([])

  // Load roster once so both tabs can use the employee list.
  useEffect(() => {
    getRoster()
      .then(setRoster)
      .catch(() => setRoster([]))
  }, [])

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold tracking-tight">HR Tools</h2>
        <p className="text-sm text-muted-foreground">
          Manage employee résumés and Slack identities.
        </p>
      </div>

      {/* Tab bar */}
      <div className="inline-flex gap-1 rounded-lg border border-border bg-muted/40 p-1">
        <TabButton
          active={tab === "resumes"}
          icon={<FileText className="h-4 w-4" />}
          label="Résumés"
          onClick={() => setTab("resumes")}
        />
        <TabButton
          active={tab === "slack"}
          icon={<Slack className="h-4 w-4" />}
          label="Slack IDs"
          onClick={() => setTab("slack")}
        />
      </div>

      {/* Tab content */}
      {tab === "resumes" && <ResumeTab roster={roster} />}
      {tab === "slack" && <SlackTab roster={roster} />}
    </div>
  )
}
