// Threads the classifier wasn't sure how to file, in one place you can work through.
//
// The mindmap already marks these with an amber dot, but finding them there means expanding
// the tree node by node — so in practice a wrong filing stayed invisible. This surfaces the
// same signal as a short worklist, and fixing one here teaches the classifier exactly as a
// correction made in the map does (see brain/mail_ingest.learn_category_keywords).
import { AlertTriangle, Check, Loader2 } from "lucide-react"
import { useCallback, useEffect, useState } from "react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { type MailReviewItem, getMailReview, reclassifyThread } from "@/lib/brainApi"

const SELECT_CLASS =
  "h-9 rounded-md border border-input px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"

export function MailReviewQueue({ onResolved }: { onResolved?: () => void | Promise<void> }) {
  const [items, setItems] = useState<MailReviewItem[]>([])
  const [categories, setCategories] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [choice, setChoice] = useState<Record<string, string>>({})
  const [busyId, setBusyId] = useState<string | null>(null)
  const [justFixed, setJustFixed] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const data = await getMailReview()
      setItems(data.threads)
      setCategories(data.categories)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't load the review list.")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  async function confirm(item: MailReviewItem, category: string) {
    setBusyId(item.id)
    setError(null)
    try {
      await reclassifyThread(item.id, category)
      // Drop it from the list immediately — it is no longer awaiting review.
      setItems((prev) => prev.filter((t) => t.id !== item.id))
      setJustFixed(item.id)
      await onResolved?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't update that thread.")
    } finally {
      setBusyId(null)
    }
  }

  if (loading) {
    return null // nothing useful to show until we know whether anything needs review
  }

  if (items.length === 0) {
    return justFixed ? (
      <Card data-testid="review-queue">
        <CardContent className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
          <Check className="h-4 w-4 text-primary" />
          All caught up — nothing left to review.
        </CardContent>
      </Card>
    ) : null
  }

  return (
    <Card data-testid="review-queue">
      <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <AlertTriangle className="h-4 w-4 text-caution-foreground" />
          Needs review
          <span className="text-sm font-normal text-muted-foreground">({items.length})</span>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <p className="text-sm text-muted-foreground">
          These didn't clearly belong anywhere. Confirm where each should live — the assistant
          learns from your choice.
        </p>
        {error && <p className="text-sm text-destructive">{error}</p>}

        <ul className="flex flex-col divide-y divide-border">
          {items.map((item) => {
            const options = Array.from(
              new Set([...categories, item.keyword_category, item.llm_category].filter(Boolean)),
            ) as string[]
            const selected = choice[item.id] ?? item.category ?? options[0] ?? ""
            return (
              <li key={item.id} className="flex flex-col gap-2 py-3">
                <div className="flex min-w-0 flex-col">
                  <span className="truncate text-sm font-medium">{item.name}</span>
                  <span className="text-xs text-muted-foreground">
                    Filed under {item.category ?? "nothing"}
                    {item.llm_category && item.keyword_category &&
                    item.llm_category !== item.keyword_category
                      ? ` — keywords suggested ${item.keyword_category}, the model said ${item.llm_category}`
                      : ""}
                  </span>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <select
                    className={SELECT_CLASS}
                    aria-label={`Category for ${item.name}`}
                    value={selected}
                    onChange={(e) => setChoice((c) => ({ ...c, [item.id]: e.target.value }))}
                  >
                    {options.map((name) => (
                      <option key={name} value={name}>
                        {name}
                      </option>
                    ))}
                  </select>
                  <Button
                    size="sm"
                    disabled={busyId === item.id || !selected}
                    onClick={() => confirm(item, selected)}
                  >
                    {busyId === item.id ? (
                      <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                    ) : (
                      <Check className="mr-1 h-4 w-4" />
                    )}
                    Confirm
                  </Button>
                </div>
              </li>
            )
          })}
        </ul>
      </CardContent>
    </Card>
  )
}
