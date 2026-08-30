import { FileText, Upload, X } from "lucide-react"
import { type FormEvent, useRef, useState } from "react"

import { type OnboardRequest, type Product, type Role, onboard } from "@/api"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

const PRODUCTS: { value: Product; label: string }[] = [
  { value: "product_one", label: "Product One" },
  { value: "product_two", label: "Product Two" },
  { value: "product_three", label: "Product Three" },
]

const ROLES: Role[] = ["admin", "gtm", "sales"]

// Resume upload constraints (client-side validation).
const RESUME_ACCEPT = ".pdf,.doc,.docx"
const RESUME_MAX_BYTES = 5 * 1024 * 1024 // 5 MB
const RESUME_EXTS = ["pdf", "doc", "docx"]

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function Onboard({ onDone }: { onDone: () => void }) {
  const [name, setName] = useState("")
  const [email, setEmail] = useState("")
  const [slack, setSlack] = useState("")
  const [role, setRole] = useState<Role>("sales")
  const [products, setProducts] = useState<Product[]>([])
  const [resume, setResume] = useState<File | null>(null)
  const [resumeError, setResumeError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  function toggleProduct(p: Product) {
    setProducts((prev) => (prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p]))
  }

  function onPickResume(e: React.ChangeEvent<HTMLInputElement>) {
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
    setBusy(true)
    setMessage(null)
    const body: OnboardRequest = {
      name,
      email,
      role,
      slack_handle: slack,
      products,
    }
    try {
      // NOTE: the resume file is captured + validated here. Persisting it needs a backend
      // multipart endpoint (backend pair's lane); once that exists, send `resume` alongside.
      const person = await onboard(body)
      const resumeNote = resume ? ` · resume "${resume.name}" attached` : ""
      setMessage(`Onboarded ${person.name} → ClickUp ${person.clickup_task_id}${resumeNote}`)
      setName("")
      setEmail("")
      setSlack("")
      setProducts([])
      clearResume()
      onDone()
    } catch {
      setMessage("Onboarding failed — check ClickUp configuration.")
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card className="max-w-lg">
      <CardHeader>
        <CardTitle>Onboard a team member</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="name">Name</Label>
            <Input id="name" value={name} onChange={(e) => setName(e.target.value)} required />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="slack">Slack handle</Label>
            <Input id="slack" value={slack} onChange={(e) => setSlack(e.target.value)} required />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="role">Role</Label>
            <select
              id="role"
              value={role}
              onChange={(e) => setRole(e.target.value as Role)}
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm capitalize shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            >
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-2">
            <Label>Products</Label>
            <div className="flex flex-wrap gap-2">
              {PRODUCTS.map((p) => (
                <Button
                  key={p.value}
                  type="button"
                  size="sm"
                  variant={products.includes(p.value) ? "default" : "outline"}
                  onClick={() => toggleProduct(p.value)}
                >
                  {p.label}
                </Button>
              ))}
            </div>
          </div>

          {/* Resume upload */}
          <div className="flex flex-col gap-2">
            <Label htmlFor="resume">Resume</Label>
            <input
              ref={fileRef}
              id="resume"
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
                  aria-label="Remove resume"
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
                  Click to upload <span className="text-foreground">resume</span>
                </span>
                <span className="text-xs">PDF, DOC, or DOCX · up to 5 MB</span>
              </button>
            )}
            {resumeError && <p className="text-sm text-destructive">{resumeError}</p>}
          </div>

          {message && <p className="text-sm text-muted-foreground">{message}</p>}
          <Button type="submit" disabled={busy}>
            {busy ? "Onboarding…" : "Onboard"}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}
