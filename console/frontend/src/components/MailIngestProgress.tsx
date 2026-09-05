// Progress for a mail ingest run.
//
// The percentage is real: it comes from the server's per-email events (brain/mail_ingest.py's
// run_iter), not a timer pretending to know. Each email costs two LLM round-trips, so a batch
// of ten runs for a while — the point is to show which one is being filed right now rather
// than leaving the UI looking frozen.
import { Loader2 } from "lucide-react"

import type { MailProgress } from "@/lib/brainApi"

/** Light-hearted, but each line still says what is actually happening. */
function caption(event: MailProgress | null): string {
  if (!event) return "Warming up…"
  switch (event.stage) {
    case "connecting":
      return "Knocking on Gmail's door…"
    case "fetched":
      return event.total === 0
        ? "Inbox is quiet — nothing new to read."
        : `Found ${event.total} email${event.total === 1 ? "" : "s"}. Rolling up sleeves…`
    case "ingesting":
      return `Reading "${truncate(event.subject)}"…`
    case "ingested":
      return event.error
        ? `Stumbled on "${truncate(event.subject)}" — carrying on…`
        : `Filed "${truncate(event.subject)}" under ${event.category ?? "…"}`
    case "done":
      return "All tidied up."
    case "failed":
      return event.error ?? "That didn't go to plan."
    default:
      return "Working…"
  }
}

function truncate(text: string | undefined, max = 42): string {
  const value = text ?? "this one"
  return value.length > max ? `${value.slice(0, max - 1)}…` : value
}

export function MailIngestProgress({ event }: { event: MailProgress | null }) {
  const total = event?.total ?? 0
  const done = event?.done ?? 0
  // Before the fetch returns there is no honest denominator, so show an indeterminate bar
  // rather than inventing a number.
  const known = total > 0
  const pct = known ? Math.round((done / total) * 100) : 0

  return (
    <div className="flex flex-col gap-1.5" data-testid="ingest-progress">
      <div className="flex items-center justify-between gap-3 text-sm">
        <span className="flex min-w-0 items-center gap-2 text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" />
          <span className="truncate">{caption(event)}</span>
        </span>
        {known && (
          <span className="shrink-0 tabular-nums font-medium" aria-live="polite">
            {pct}%
          </span>
        )}
      </div>

      <div
        className="h-1.5 w-full overflow-hidden rounded-full bg-secondary"
        role="progressbar"
        aria-valuenow={known ? pct : undefined}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Mail ingest progress"
      >
        <div
          className={[
            "h-full rounded-full bg-primary transition-[width] duration-300 ease-out",
            known ? "" : "w-1/3 animate-pulse",
          ].join(" ")}
          style={known ? { width: `${pct}%` } : undefined}
        />
      </div>

      {known && (
        <p className="text-xs text-muted-foreground tabular-nums">
          {done} of {total} processed
        </p>
      )}
    </div>
  )
}
