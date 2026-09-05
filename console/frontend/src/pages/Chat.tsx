// The chat-style lander: a persistent left sidebar of past conversations (ChatGPT/Claude.ai
// style) plus a full-height thread on the right. Sessions/messages are persisted server-side
// (console/backend/chat.py) instead of the old MailChat.tsx's ephemeral in-memory state, so a
// refresh no longer loses the conversation and past conversations are browsable.
import { Check, MessageSquarePlus, Pencil, Trash2, X } from "lucide-react"
import { useEffect, useRef, useState } from "react"

import {
  type ChatSession,
  createChatSession,
  deleteChatSession,
  getChatSession,
  listChatSessions,
  postChatMessage,
  renameChatSession,
} from "@/api"
import { ChatThread, type ThreadMessage } from "@/components/ChatThread"
import { loadProfileDetails } from "@/lib/profileDetails"

function relativeTime(iso: string): string {
  // The API serializes naive UTC timestamps (SQLite has no timezone type), which JS would
  // otherwise parse as local time — making a just-created chat read as hours old.
  const utc = /[Z+]|-\d{2}:\d{2}$/.test(iso) ? iso : `${iso}Z`
  const diffMs = Date.now() - new Date(utc).getTime()
  const minutes = Math.round(diffMs / 60000)
  if (minutes < 1) return "just now"
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.round(hours / 24)
  return `${days}d ago`
}

export function Chat({
  seed,
  onSeedConsumed,
}: {
  /** A question handed over from the Mail tab's "Ask about this" — see App.tsx. */
  seed?: string | null
  onSeedConsumed?: () => void
} = {}) {
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [sessionsLoading, setSessionsLoading] = useState(true)
  const [activeId, setActiveId] = useState<number | null>(null)
  const [messages, setMessages] = useState<ThreadMessage[]>([])
  const [messagesLoading, setMessagesLoading] = useState(false)
  const [input, setInput] = useState("")
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [renamingId, setRenamingId] = useState<number | null>(null)
  const [renameValue, setRenameValue] = useState("")
  const [query, setQuery] = useState("")
  // The question behind a failed answer, so it can be retried without retyping.
  const [failedQuestion, setFailedQuestion] = useState<string | null>(null)
  // Bumped whenever the message list is mutated locally. A history fetch that started before
  // the bump is stale by the time it resolves, and applying it would wipe an optimistically
  // rendered message the user just sent.
  const loadSeq = useRef(0)

  useEffect(() => {
    let cancelled = false
    listChatSessions()
      .then((list) => {
        if (cancelled) return
        setSessions(list)
        if (list.length > 0) setActiveId(list[0].id)
      })
      .catch(() => {
        if (!cancelled) setError("Couldn't load your past chats.")
      })
      .finally(() => {
        if (!cancelled) setSessionsLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (activeId === null) {
      setMessages([])
      return
    }
    let cancelled = false
    const seq = ++loadSeq.current
    setMessagesLoading(true)
    getChatSession(activeId)
      .then((session) => {
        if (cancelled || seq !== loadSeq.current) return
        setMessages(
          session.messages.map((m) => ({ id: m.id, role: m.role, content: m.content })),
        )
      })
      .catch(() => {
        if (!cancelled) setError("Couldn't load that conversation.")
      })
      .finally(() => {
        if (!cancelled) setMessagesLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [activeId])

  // A question arriving from the Mail tab starts a fresh conversation with it pre-filled —
  // deliberately not auto-sent, so it can be reworded before spending an LLM call.
  useEffect(() => {
    if (!seed) return
    setActiveId(null)
    setMessages([])
    setInput(seed)
    onSeedConsumed?.()
    // onSeedConsumed is a stable setter from App; re-running on its identity would clear the
    // seed before it is applied.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seed])

  const needle = query.trim().toLowerCase()
  const visibleSessions = needle
    ? sessions.filter((s) => (s.title ?? "New chat").toLowerCase().includes(needle))
    : sessions

  async function handleNewChat() {
    setError(null)
    // The active session is already an unused blank one — don't pile up another empty
    // "New chat" row in the history for every click.
    if (activeId !== null && messages.length === 0 && !messagesLoading) return
    try {
      const session = await createChatSession()
      setSessions((prev) => [session, ...prev])
      setActiveId(session.id)
      setMessages([])
    } catch {
      setError("Couldn't start a new chat.")
    }
  }

  async function handleSend(retryText?: string) {
    const text = (retryText ?? input).trim()
    if (!text || pending) return
    setError(null)
    setFailedQuestion(null)
    if (!retryText) setInput("")

    let sessionId = activeId
    try {
      if (sessionId === null) {
        const session = await createChatSession()
        setSessions((prev) => [session, ...prev])
        setActiveId(session.id)
        sessionId = session.id
      }
    } catch {
      setError("Couldn't start a new chat.")
      setInput(text)
      return
    }

    // Invalidate any history fetch still in flight, so it can't overwrite this message.
    loadSeq.current++
    setMessages((prev) => [...prev, { id: `pending-${Date.now()}`, role: "user", content: text }])
    setPending(true)
    try {
      const details = loadProfileDetails().map(({ key, value }) => ({ key, value }))
      const reply = await postChatMessage(sessionId, text, details)
      setMessages((prev) => [...prev, { id: reply.id, role: "assistant", content: reply.content }])
      const updated = await listChatSessions()
      setSessions(updated)
    } catch (err) {
      const detail = err instanceof Error ? err.message : "Something went wrong."
      setMessages((prev) => [
        ...prev,
        { id: `error-${Date.now()}`, role: "assistant", content: `Couldn't get an answer: ${detail}` },
      ])
      // The question was persisted server-side but the answer wasn't — offer a retry rather
      // than leaving a dead end in the transcript.
      setFailedQuestion(text)
    } finally {
      setPending(false)
    }
  }

  function startRename(session: ChatSession) {
    setRenamingId(session.id)
    setRenameValue(session.title ?? "")
  }

  async function commitRename() {
    if (renamingId === null) return
    const title = renameValue.trim()
    const id = renamingId
    setRenamingId(null)
    if (!title) return
    try {
      const updated = await renameChatSession(id, title)
      setSessions((prev) => prev.map((s) => (s.id === id ? updated : s)))
    } catch {
      setError("Couldn't rename that chat.")
    }
  }

  async function handleDelete(id: number) {
    // Deleting a conversation drops its whole transcript server-side and cannot be undone, so
    // it should never be one stray click away.
    const session = sessions.find((s) => s.id === id)
    const label = session?.title ? `“${session.title}”` : "this chat"
    if (!window.confirm(`Delete ${label}? This can't be undone.`)) return
    try {
      await deleteChatSession(id)
      setSessions((prev) => prev.filter((s) => s.id !== id))
      if (activeId === id) {
        setActiveId(null)
        setMessages([])
      }
    } catch {
      setError("Couldn't delete that chat.")
    }
  }

  return (
    <div className="flex h-full min-h-0 w-full">
      <aside className="flex h-full w-72 shrink-0 flex-col border-r border-border bg-card">
        <div className="p-3">
          <button
            type="button"
            onClick={handleNewChat}
            className="flex w-full items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm font-medium text-foreground transition-colors hover:bg-accent"
          >
            <MessageSquarePlus className="h-4 w-4" />
            New chat
          </button>
        </div>

        {sessions.length > 0 && (
          <div className="px-3 pb-2">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search chats…"
              aria-label="Search chats"
              className="w-full rounded-lg border border-border bg-background px-2.5 py-1.5 text-sm outline-none placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring"
            />
          </div>
        )}

        <div className="flex-1 overflow-y-auto px-2 pb-3">
          {sessionsLoading ? (
            <p className="px-2 py-2 text-sm text-muted-foreground">Loading…</p>
          ) : sessions.length === 0 ? (
            <p className="px-2 py-2 text-sm text-muted-foreground">
              No conversations yet — send a message to start one.
            </p>
          ) : visibleSessions.length === 0 ? (
            <p className="px-2 py-2 text-sm text-muted-foreground">No chats match “{query}”.</p>
          ) : (
            <ul className="flex flex-col gap-0.5">
              {visibleSessions.map((s) => (
                <li key={s.id}>
                  {renamingId === s.id ? (
                    <div className="flex items-center gap-1 rounded-lg px-2 py-1.5">
                      <input
                        autoFocus
                        value={renameValue}
                        onChange={(e) => setRenameValue(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") commitRename()
                          if (e.key === "Escape") setRenamingId(null)
                        }}
                        className="min-w-0 flex-1 rounded border border-input bg-background px-2 py-1 text-sm outline-none"
                      />
                      <button type="button" onClick={commitRename} aria-label="Save" className="text-muted-foreground hover:text-foreground">
                        <Check className="h-4 w-4" />
                      </button>
                      <button type="button" onClick={() => setRenamingId(null)} aria-label="Cancel" className="text-muted-foreground hover:text-foreground">
                        <X className="h-4 w-4" />
                      </button>
                    </div>
                  ) : (
                    <div
                      className={[
                        "group flex items-center gap-1 rounded-lg px-2 py-1.5 text-sm",
                        activeId === s.id ? "bg-accent text-accent-foreground" : "text-foreground hover:bg-accent/60",
                      ].join(" ")}
                    >
                      <button
                        type="button"
                        onClick={() => setActiveId(s.id)}
                        className="min-w-0 flex-1 truncate text-left"
                      >
                        <span className="block truncate">{s.title || "New chat"}</span>
                        <span className="block truncate text-xs text-muted-foreground">
                          {relativeTime(s.updated_at)}
                        </span>
                      </button>
                      <button
                        type="button"
                        onClick={() => startRename(s)}
                        aria-label="Rename chat"
                        className="hidden shrink-0 text-muted-foreground hover:text-foreground group-hover:block"
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDelete(s.id)}
                        aria-label="Delete chat"
                        className="hidden shrink-0 text-muted-foreground hover:text-destructive group-hover:block"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </aside>

      <div className="flex h-full min-h-0 flex-1 flex-col">
        {error && (
          <p className="border-b border-border bg-destructive/10 px-5 py-2 text-sm text-destructive">
            {error}
          </p>
        )}
        {/* The composer stays mounted while history loads. Swapping it out for a spinner
            unmounted the controlled textarea and silently discarded anything typed meanwhile. */}
        {failedQuestion && !pending && (
          <div className="flex items-center justify-between gap-3 border-b border-border bg-caution px-5 py-2 text-sm text-caution-foreground">
            <span>That answer didn't come through.</span>
            <button
              type="button"
              onClick={() => handleSend(failedQuestion)}
              className="shrink-0 font-medium underline underline-offset-4"
            >
              Retry
            </button>
          </div>
        )}
        <ChatThread
          messages={messages}
          pending={pending}
          loading={messagesLoading}
          input={input}
          onInputChange={setInput}
          onSend={handleSend}
          emptyStatePrompt={"Ask something like \"What did Hevo Data's email say?\""}
        />
      </div>
    </div>
  )
}
