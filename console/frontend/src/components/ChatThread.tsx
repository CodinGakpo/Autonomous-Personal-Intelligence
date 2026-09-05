// The message list + composer, styled after Claude's chat screen: plain text for assistant
// messages, a rounded bubble for user messages, a pill-shaped composer pinned to the bottom.
// Extracted from the old MailChat.tsx so both a full-page chat (pages/Chat.tsx) and any future
// smaller usage can share the same rendering without duplicating this markup.
import { ArrowUp, Loader2 } from "lucide-react"
import { useEffect, useRef } from "react"

export interface ThreadMessage {
  id: number | string
  role: "user" | "assistant"
  content: string
}

interface ChatThreadProps {
  messages: ThreadMessage[]
  pending: boolean
  input: string
  onInputChange: (value: string) => void
  onSend: () => void
  emptyStatePrompt: string
  disabled?: boolean
  /** History is being fetched. Shown inside the transcript so the composer stays mounted. */
  loading?: boolean
}

export function ChatThread({
  messages,
  pending,
  input,
  onInputChange,
  onSend,
  emptyStatePrompt,
  disabled,
  loading,
}: ChatThreadProps) {
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" })
  }, [messages, pending])

  return (
    <div className="flex h-full w-full flex-col">
      <div ref={scrollRef} data-testid="chat-thread" className="flex-1 overflow-y-auto px-5 py-6">
        {loading ? (
          <div className="flex h-full items-center justify-center">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : messages.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-1 text-center">
            <p className="text-sm text-muted-foreground">{emptyStatePrompt}</p>
          </div>
        ) : (
          <div className="mx-auto flex w-full max-w-2xl flex-col gap-5">
            {messages.map((m) => (
              <div key={m.id} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
                <div
                  className={
                    m.role === "user"
                      ? "max-w-[85%] rounded-2xl bg-secondary px-4 py-2 text-sm text-secondary-foreground"
                      : "max-w-[85%] whitespace-pre-wrap text-sm leading-relaxed text-foreground"
                  }
                >
                  {m.content}
                </div>
              </div>
            ))}
            {pending && (
              <div className="flex justify-start">
                <div className="max-w-[85%] text-sm leading-relaxed text-muted-foreground">
                  Thinking…
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      <div className="relative px-5 pb-5 pt-2">
        <div className="mx-auto flex w-full max-w-2xl items-end gap-2 rounded-3xl border border-input bg-background px-3 py-2 shadow-sm focus-within:ring-2 focus-within:ring-ring">
          <textarea
            value={input}
            onChange={(e) => onInputChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault()
                onSend()
              }
            }}
            placeholder="Ask a question…"
            rows={1}
            disabled={disabled}
            className="max-h-32 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm outline-none placeholder:text-muted-foreground disabled:opacity-50"
          />
          <button
            type="button"
            // Wrapped, not passed directly: onClick would hand the MouseEvent to onSend's
            // first parameter, which the caller uses for retry text.
            onClick={() => onSend()}
            disabled={disabled || !input.trim() || pending}
            aria-label="Send"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground transition-opacity disabled:opacity-40"
          >
            <ArrowUp className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  )
}
