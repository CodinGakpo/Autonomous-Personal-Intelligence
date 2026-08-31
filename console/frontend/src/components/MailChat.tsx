// Chat panel styled after Claude's chat screen: plain text for assistant messages, a
// rounded bubble for user messages, a pill-shaped composer pinned to the bottom. Sends real
// questions to brain/viz_server.py's /api/mail/ask, folding in the "About you" details from
// the Profile page as light personal context.
import { ArrowUp } from "lucide-react"
import { useEffect, useRef, useState } from "react"

import { askMail } from "@/lib/brainApi"
import { loadProfileDetails } from "@/lib/profileDetails"

interface ChatMessage {
  id: number
  role: "user" | "assistant"
  content: string
}

export function MailChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState("")
  const [pending, setPending] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" })
  }, [messages, pending])

  async function send() {
    const text = input.trim()
    if (!text || pending) return
    setMessages((prev) => [...prev, { id: Date.now(), role: "user", content: text }])
    setInput("")
    setPending(true)
    try {
      const details = loadProfileDetails().map(({ key, value }) => ({ key, value }))
      const { answer } = await askMail(text, details)
      setMessages((prev) => [...prev, { id: Date.now() + 1, role: "assistant", content: answer }])
    } catch (err) {
      const detail = err instanceof Error ? err.message : "Something went wrong."
      setMessages((prev) => [
        ...prev,
        { id: Date.now() + 1, role: "assistant", content: `Couldn't get an answer: ${detail}` },
      ])
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="relative flex h-[640px] w-full flex-col overflow-hidden rounded-xl border bg-card">
      <div className="border-b px-5 py-3">
        <p className="text-sm font-medium">Ask about your mail</p>
        <p className="text-xs text-muted-foreground">Answers use your ingested mail</p>
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
            disabled={!input.trim() || pending}
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
