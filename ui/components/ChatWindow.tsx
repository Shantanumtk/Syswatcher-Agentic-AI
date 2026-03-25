import { useState, useRef, useEffect, KeyboardEvent } from "react"
import { Message, askAgent, runSweep } from "../lib/api"
import MessageBubble from "./MessageBubble"

interface Props {
  serverName: string
  threadId:   string
}

const SUGGESTIONS = [
  "Is everything ok?",
  "What's the CPU usage?",
  "Did all crons run today?",
  "Any auth failures?",
  "Show disk usage",
  "Run a full sweep",
]

export default function ChatWindow({ serverName, threadId }: Props) {
  const [messages,  setMessages]  = useState<Message[]>([])
  const [input,     setInput]     = useState("")
  const [loading,   setLoading]   = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  // Scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  // Welcome message
  useEffect(() => {
    setMessages([{
      id:      "welcome",
      role:    "agent",
      content: `Hi! I'm SysWatcher monitoring **${serverName}**.\n\nAsk me anything about the server — health, crons, disk, CPU, logs — or type "run a full sweep" to check everything now.`,
      ts:      new Date(),
    }])
  }, [serverName])

  const addMessage = (msg: Omit<Message, "id">) => {
    setMessages(prev => [...prev, { ...msg, id: crypto.randomUUID() }])
  }

  const send = async (text: string) => {
    const question = text.trim()
    if (!question || loading) return

    setInput("")
    addMessage({ role: "user", content: question, ts: new Date() })
    setLoading(true)

    try {
      // Handle "run a full sweep" specially
      if (question.toLowerCase().includes("full sweep") ||
          question.toLowerCase().includes("run sweep")) {
        addMessage({
          role:    "agent",
          content: "Running full sweep — this may take 15–30 seconds…",
          ts:      new Date(),
        })
        const result = await runSweep(serverName)
        addMessage({
          role:     "agent",
          content:  result.report,
          severity: result.severity,
          ts:       new Date(),
        })
      } else {
        const result = await askAgent(question, threadId, serverName)
        addMessage({
          role:     "agent",
          content:  result.answer,
          severity: result.severity,
          ts:       new Date(),
        })
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Unknown error"
      addMessage({
        role:    "agent",
        content: `Error: ${msg}\n\nMake sure the agent is running at ${process.env.NEXT_PUBLIC_API_URL}`,
        ts:      new Date(),
      })
    } finally {
      setLoading(false)
    }
  }

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      send(input)
    }
  }

  return (
    <div style={{
      display:       "flex",
      flexDirection: "column",
      height:        "100%",
      background:    "#13131f",
    }}>
      {/* Messages */}
      <div style={{
        flex:       1,
        overflowY:  "auto",
        padding:    "20px 16px",
      }}>
        {messages.map(m => (
          <MessageBubble key={m.id} message={m} />
        ))}

        {/* Typing indicator */}
        {loading && (
          <div style={{
            display:    "flex",
            alignItems: "center",
            gap:        "6px",
            color:      "#6b6b88",
            fontSize:   "13px",
            marginBottom: "12px",
          }}>
            <span style={{
              width: "28px", height: "28px", borderRadius: "50%",
              background: "#4f46e5", display: "flex",
              alignItems: "center", justifyContent: "center",
              fontSize: "12px", color: "white", flexShrink: 0,
            }}>SW</span>
            <span>Thinking…</span>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Suggestions */}
      {messages.length <= 1 && (
        <div style={{
          display:   "flex",
          flexWrap:  "wrap",
          gap:       "8px",
          padding:   "0 16px 12px",
        }}>
          {SUGGESTIONS.map(s => (
            <button
              key={s}
              onClick={() => send(s)}
              disabled={loading}
              style={{
                background:   "#2d2d3f",
                border:       "1px solid #3d3d5c",
                color:        "#a0a0b8",
                padding:      "6px 12px",
                borderRadius: "16px",
                fontSize:     "12px",
                cursor:       "pointer",
                transition:   "background 0.15s",
              }}
            >
              {s}
            </button>
          ))}
        </div>
      )}

      {/* Input bar */}
      <div style={{
        display:      "flex",
        alignItems:   "flex-end",
        gap:          "10px",
        padding:      "12px 16px",
        borderTop:    "1px solid #2d2d3f",
        background:   "#1e1e2e",
      }}>
        <textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Ask anything about the server… (Enter to send, Shift+Enter for newline)"
          disabled={loading}
          rows={1}
          style={{
            flex:         1,
            background:   "#2d2d3f",
            border:       "1px solid #3d3d5c",
            borderRadius: "12px",
            color:        "#e0e0f0",
            padding:      "10px 14px",
            fontSize:     "14px",
            resize:       "none",
            outline:      "none",
            lineHeight:   "1.5",
            fontFamily:   "inherit",
            maxHeight:    "120px",
            overflowY:    "auto",
          }}
        />
        <button
          onClick={() => send(input)}
          disabled={loading || !input.trim()}
          style={{
            background:   loading || !input.trim() ? "#2d2d3f" : "#4f46e5",
            border:       "none",
            borderRadius: "10px",
            color:        loading || !input.trim() ? "#4a4a68" : "white",
            padding:      "10px 18px",
            fontSize:     "14px",
            fontWeight:   600,
            cursor:       loading || !input.trim() ? "not-allowed" : "pointer",
            transition:   "background 0.15s",
            whiteSpace:   "nowrap",
          }}
        >
          Send
        </button>
      </div>
    </div>
  )
}
