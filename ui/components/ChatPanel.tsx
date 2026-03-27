import { useState, useRef, useEffect, KeyboardEvent } from "react"
import { askAgent, runSweep } from "../lib/api"

interface Message {
  id: string; role: "user"|"agent"; content: string
  severity?: string; ts: Date; thinking?: boolean
}
interface Props { serverName: string; threadId: string; onMessage: (s: string, p: string) => void }

export default function ChatPanel({ serverName, threadId, onMessage }: Props) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState("")
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior:"smooth" }) }, [messages])

  useEffect(() => {
    setMessages([{ id:"welcome", role:"agent",
      content:`Connected to **${serverName}**. Ready for your commands.`, ts:new Date() }])
  }, [serverName])

  useEffect(() => {
    const handler = (e: Event) => { setInput((e as CustomEvent).detail); textareaRef.current?.focus() }
    window.addEventListener("syswatcher:prompt", handler)
    return () => window.removeEventListener("syswatcher:prompt", handler)
  }, [])

  const addMsg = (msg: Omit<Message,"id">) =>
    setMessages(prev => [...prev, { ...msg, id: Math.random().toString(36).slice(2)+Date.now() }])

  const send = async (text: string) => {
    const q = text.trim(); if (!q || loading) return
    setInput("")
    addMsg({ role:"user", content:q, ts:new Date() })
    setLoading(true)
    const thinkId = Math.random().toString(36).slice(2)
    setMessages(prev => [...prev, { id:thinkId, role:"agent", content:"", ts:new Date(), thinking:true }])
    try {
      let result: { answer?: string; report?: string; severity?: string }
      if (q.toLowerCase().includes("full sweep") || q.toLowerCase().includes("run sweep")) {
        result = await runSweep(serverName); result.answer = result.report
      } else {
        result = await askAgent(q, threadId, serverName)
      }
      setMessages(prev => prev.filter(m => m.id !== thinkId))
      addMsg({ role:"agent", content:result.answer||"", severity:result.severity, ts:new Date() })
      onMessage(serverName, q.slice(0,40))
    } catch (e: unknown) {
      setMessages(prev => prev.filter(m => m.id !== thinkId))
      addMsg({ role:"agent", content:`Error: ${e instanceof Error ? e.message : "Connection failed"}`, severity:"critical", ts:new Date() })
    } finally { setLoading(false) }
  }

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input) }
  }

  return (
    <div style={{ flex:1, display:"flex", flexDirection:"column", minWidth:0 }}>
      <div style={{ flex:1, overflowY:"auto", padding:"20px 0", scrollbarWidth:"thin", scrollbarColor:"rgba(255,255,255,0.08) transparent" }}>
        {messages.map(m => <MessageRow key={m.id} msg={m} />)}
        <div ref={bottomRef} />
      </div>
      <div style={{ padding:"12px 20px 16px", borderTop:"1px solid rgba(255,255,255,0.05)", background:"rgba(5,5,8,0.6)", backdropFilter:"blur(12px)" }}>
        <div style={{ display:"flex", gap:"10px", alignItems:"flex-end",
          background:"rgba(255,255,255,0.04)", border:"1px solid rgba(255,255,255,0.08)", borderRadius:"12px", padding:"10px 12px" }}>
          <span style={{ fontFamily:"'JetBrains Mono',monospace", fontSize:"14px", color:"#4f46e5", flexShrink:0, paddingBottom:"2px" }}>›</span>
          <textarea ref={textareaRef} value={input} onChange={e => setInput(e.target.value)} onKeyDown={onKeyDown}
            disabled={loading} placeholder={`Query ${serverName}...`} rows={1}
            style={{ flex:1, background:"transparent", border:"none", outline:"none", color:"#e2e8f0", fontSize:"14px",
              resize:"none", fontFamily:"'JetBrains Mono',monospace", lineHeight:"1.5", maxHeight:"100px", overflowY:"auto" }} />
          <button onClick={() => send(input)} disabled={loading||!input.trim()} style={{
            width:"32px", height:"32px", borderRadius:"8px", border:"none",
            background: loading||!input.trim() ? "rgba(255,255,255,0.04)" : "linear-gradient(135deg,#6366f1,#06b6d4)",
            color: loading||!input.trim() ? "#334155" : "white",
            cursor: loading||!input.trim() ? "not-allowed" : "pointer",
            display:"flex", alignItems:"center", justifyContent:"center", fontSize:"16px", flexShrink:0,
            boxShadow: loading||!input.trim() ? "none" : "0 0 16px rgba(99,102,241,0.4)" }}>↑</button>
        </div>
        <div style={{ marginTop:"6px", fontSize:"10px", color:"#1e293b", textAlign:"center", fontFamily:"'JetBrains Mono',monospace" }}>
          Enter to send · Shift+Enter for newline · ⌘ Commands for prompt library
        </div>
      </div>
    </div>
  )
}

function MessageRow({ msg }: { msg: Message }) {
  const isUser = msg.role === "user"
  const SEV: Record<string,{color:string;bg:string;label:string}> = {
    critical:{color:"#ef4444",bg:"rgba(239,68,68,0.08)",label:"CRITICAL"},
    warn:{color:"#f59e0b",bg:"rgba(245,158,11,0.08)",label:"WARN"},
    healthy:{color:"#10b981",bg:"rgba(16,185,129,0.08)",label:"HEALTHY"},
  }
  const sev = msg.severity ? SEV[msg.severity] : null

  if (msg.thinking) return (
    <div style={{ padding:"6px 20px", display:"flex", alignItems:"center", gap:"10px", marginBottom:"8px" }}>
      <AgentAvatar />
      <div style={{ display:"flex", gap:"4px", alignItems:"center", padding:"10px 14px",
        background:"rgba(255,255,255,0.04)", border:"1px solid rgba(255,255,255,0.06)", borderRadius:"4px 12px 12px 12px" }}>
        {[0,1,2].map(i => (
          <div key={i} style={{ width:"5px", height:"5px", borderRadius:"50%", background:"#6366f1",
            animation:`swbounce 1.2s ease-in-out ${i*0.2}s infinite` }} />
        ))}
      </div>
      <style>{`@keyframes swbounce{0%,60%,100%{transform:translateY(0)}30%{transform:translateY(-6px)}}`}</style>
    </div>
  )

  return (
    <div style={{ padding:"4px 20px", display:"flex", justifyContent: isUser?"flex-end":"flex-start",
      gap:"10px", alignItems:"flex-start", marginBottom:"8px" }}>
      {!isUser && <AgentAvatar />}
      <div style={{ maxWidth:"72%", minWidth:"60px" }}>
        {sev && msg.severity !== "healthy" && (
          <div style={{ display:"inline-flex", alignItems:"center", gap:"5px", padding:"2px 8px", borderRadius:"4px",
            marginBottom:"5px", background:sev.bg, color:sev.color, border:`1px solid ${sev.color}30`,
            fontSize:"10px", fontWeight:700, fontFamily:"'JetBrains Mono',monospace", letterSpacing:"1px" }}>
            <span style={{ width:"5px", height:"5px", borderRadius:"50%", background:sev.color, display:"inline-block" }} />
            {sev.label}
          </div>
        )}
        <div style={{
          padding: isUser ? "10px 14px" : "12px 16px",
          borderRadius: isUser ? "14px 14px 4px 14px" : "4px 14px 14px 14px",
          background: isUser ? "linear-gradient(135deg,#4f46e5,#6366f1)"
            : sev && msg.severity !== "healthy" ? sev.bg : "rgba(255,255,255,0.04)",
          border: isUser ? "none" : sev && msg.severity !== "healthy"
            ? `1px solid ${sev.color}20` : "1px solid rgba(255,255,255,0.06)",
          color:"#e2e8f0", fontSize:"13px", lineHeight:"1.7",
          fontFamily:"'JetBrains Mono',monospace", whiteSpace:"pre-wrap", wordBreak:"break-word",
          boxShadow: isUser ? "0 4px 20px rgba(99,102,241,0.25)" : "none" }}>
          {renderContent(msg.content)}
        </div>
        <div style={{ fontSize:"10px", color:"#1e293b", marginTop:"3px",
          textAlign: isUser?"right":"left", fontFamily:"'JetBrains Mono',monospace" }}>
          {msg.ts.toLocaleTimeString()}
        </div>
      </div>
      {isUser && (
        <div style={{ width:"28px", height:"28px", borderRadius:"50%", flexShrink:0,
          background:"rgba(99,102,241,0.2)", border:"1px solid rgba(99,102,241,0.3)",
          display:"flex", alignItems:"center", justifyContent:"center",
          fontSize:"11px", fontWeight:700, color:"#818cf8" }}>U</div>
      )}
    </div>
  )
}

function AgentAvatar() {
  return (
    <div style={{ width:"28px", height:"28px", borderRadius:"8px", flexShrink:0,
      background:"linear-gradient(135deg,#6366f1,#06b6d4)", display:"flex",
      alignItems:"center", justifyContent:"center", fontSize:"11px",
      fontWeight:800, color:"white", boxShadow:"0 0 12px rgba(99,102,241,0.3)" }}>SW</div>
  )
}

function renderContent(content: string) {
  const parts = content.split(/(\*\*[^*]+\*\*)/)
  return parts.map((part, i) =>
    part.startsWith("**") && part.endsWith("**")
      ? <strong key={i} style={{ color:"#f1f5f9", fontWeight:700 }}>{part.slice(2,-2)}</strong>
      : <span key={i}>{part}</span>
  )
}
