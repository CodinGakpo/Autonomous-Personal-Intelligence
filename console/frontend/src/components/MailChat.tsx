// UI-only chat panel styled after Claude's chat screen: plain message text (no bubble noise),
// generous spacing, a pill-shaped composer pinned to the bottom. Sending isn't wired to a
// backend yet — it just surfaces a "work in progress" notice next to the composer.
import { ArrowUp } from "lucide-react"
import { useEffect, useRef, useState } from "react"

interface ChatMessage {
  id: number
  role: "user" | "assistant"
  content: string
}

export function MailChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState("")
  const [noticeVisible, setNoticeVisible] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" })
  }, [messages])

  useEffect(() => {
    if (!noticeVisible) return
    const t = setTimeout(() => setNoticeVisible(false), 2600)
    return () => clearTimeout(t)
  }, [noticeVisible])

  function send() {
    const text = input.trim()
    if (!text) return
    setMessages((prev) => [...prev, { id: Date.now(), role: "user", content: text }])
    setInput("")
    setNoticeVisible(true)
  }

  return (
    <div className="relative flex h-[640px] w-full flex-col overflow-hidden rounded-xl border bg-card">
      <div className="border-b px-5 py-3">
        <p className="text-sm font-medium">Ask about your mail</p>
        <p className="text-xs text-muted-foreground">UI preview — answering isn't connected yet</p>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto px-5 py-6">
        {messages.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-1 text-center">
            <p className="text-sm text-muted-foreground">
              Ask something like "What did Hevo Data's email say?"
            </p>
          </div>
        ) : (
          <div className="mx-auto flex max-w-md flex-col gap-5">
            {messages.map((m) => (
              <div key={m.id} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
                <div
                  className={
                    m.role === "user"
                      ? "max-w-[85%] rounded-2xl bg-secondary px-4 py-2 text-sm text-secondary-foreground"
                      : "max-w-[85%] text-sm leading-relaxed text-foreground"
                  }
                >
                  {m.content}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="relative px-5 pb-5 pt-2">
        {noticeVisible && (
          <div className="pointer-events-none absolute inset-x-5 bottom-[calc(100%+0.5rem)] flex justify-center">
            <div className="pointer-events-auto rounded-full border border-border bg-caution px-3.5 py-1.5 text-sm font-medium text-caution-foreground shadow-lg">
              Not connected yet — this is a preview
            </div>
          </div>
        )}
        <div className="flex items-end gap-2 rounded-3xl border border-input bg-background px-3 py-2 shadow-sm focus-within:ring-2 focus-within:ring-ring">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault()
                send()
              }
            }}
            placeholder="Ask a question…"
            rows={1}
            className="max-h-32 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm outline-none placeholder:text-muted-foreground"
          />
          <button
            type="button"
            onClick={send}
            disabled={!input.trim()}
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
