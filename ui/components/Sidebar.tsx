import { StatusResponse } from "../lib/api"

interface Props {
  servers: string[]
  activeServer: string
  onServerChange: (s: string) => void
  chatHistory: {id:string;server:string;preview:string;ts:Date}[]
  activeChat: string
  onChatSelect: (id: string) => void
  status: StatusResponse | null
}

const STATUS_COLOR: Record<string,string> = { healthy:"#10b981", warn:"#f59e0b", critical:"#ef4444" }

export default function Sidebar({ servers, activeServer, onServerChange, chatHistory, activeChat, onChatSelect, status }: Props) {
  return (
    <div style={{ width:"220px", flexShrink:0, display:"flex", flexDirection:"column",
      borderRight:"1px solid rgba(255,255,255,0.05)", background:"rgba(8,8,12,0.9)", position:"relative", zIndex:1 }}>

      <div style={{ padding:"16px 16px 12px", borderBottom:"1px solid rgba(255,255,255,0.05)" }}>
        <div style={{ display:"flex", alignItems:"center", gap:"10px" }}>
          <div style={{ width:"32px", height:"32px", borderRadius:"8px", flexShrink:0,
            background:"linear-gradient(135deg,#6366f1,#06b6d4)", display:"flex", alignItems:"center",
            justifyContent:"center", fontSize:"12px", fontWeight:800, color:"white",
            boxShadow:"0 0 16px rgba(99,102,241,0.4)" }}>SW</div>
          <div style={{ display:"flex", flexDirection:"column", justifyContent:"center" }}>
            <div style={{ fontSize:"14px", fontWeight:800, color:"#f1f5f9", letterSpacing:"-0.3px", lineHeight:"1.2" }}>SysWatcher</div>
            <div style={{ fontSize:"10px", color:"#475569", fontFamily:"'JetBrains Mono',monospace", letterSpacing:"0.5px", lineHeight:"1.2" }}>AI MONITOR</div>
          </div>
        </div>
      </div>

      <div style={{ padding:"12px 12px 8px" }}>
        <div style={{ fontSize:"10px", fontWeight:700, color:"#334155", letterSpacing:"1.5px", marginBottom:"6px", paddingLeft:"4px" }}>SERVERS</div>
        {servers.map(s => {
          const isActive = s === activeServer
          const sColor = isActive ? (STATUS_COLOR[status?.overall || "healthy"]) : "#334155"
          return (
            <button key={s} onClick={() => onServerChange(s)} style={{
              width:"100%", display:"flex", alignItems:"center", gap:"8px",
              padding:"7px 8px", borderRadius:"6px", border:"none", cursor:"pointer",
              background: isActive ? "rgba(99,102,241,0.12)" : "transparent",
              color: isActive ? "#e2e8f0" : "#64748b",
              fontSize:"13px", fontWeight: isActive ? 600 : 400,
              textAlign:"left", marginBottom:"2px" }}>
              <div style={{ width:"6px", height:"6px", borderRadius:"50%", flexShrink:0,
                background:sColor, boxShadow: isActive ? `0 0 6px ${sColor}` : "none" }} />
              <span style={{ fontFamily:"'JetBrains Mono',monospace", fontSize:"12px" }}>{s}</span>
              {isActive && <div style={{ marginLeft:"auto", width:"4px", height:"4px", borderRadius:"50%", background:"#6366f1" }} />}
            </button>
          )
        })}
      </div>

      <div style={{ height:"1px", background:"rgba(255,255,255,0.04)", margin:"4px 12px" }} />

      <div style={{ padding:"8px 12px", flex:1, overflowY:"auto" }}>
        <div style={{ fontSize:"10px", fontWeight:700, color:"#334155", letterSpacing:"1.5px", marginBottom:"6px", paddingLeft:"4px" }}>RECENT CHATS</div>
        {chatHistory.length === 0 ? (
          <div style={{ padding:"12px 8px", fontSize:"11px", color:"#1e293b", fontFamily:"'JetBrains Mono',monospace", textAlign:"center" }}>No history yet</div>
        ) : chatHistory.map(h => (
          <button key={h.id} onClick={() => onChatSelect(h.id)} style={{
            width:"100%", padding:"7px 8px", borderRadius:"6px", border:"none", cursor:"pointer", textAlign:"left",
            background: activeChat === h.id ? "rgba(99,102,241,0.1)" : "transparent",
            color: activeChat === h.id ? "#a5b4fc" : "#475569", marginBottom:"2px" }}>
            <div style={{ fontSize:"11px", fontWeight:500, marginBottom:"2px", overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{h.preview}</div>
            <div style={{ fontSize:"10px", color:"#1e293b", fontFamily:"'JetBrains Mono',monospace" }}>{h.server} · {h.ts.toLocaleTimeString()}</div>
          </button>
        ))}
      </div>

      {status && (
        <div style={{ padding:"10px 12px", borderTop:"1px solid rgba(255,255,255,0.04)" }}>
          <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:"6px" }}>
            {[{label:"CRITICAL",value:status.critical_count,color:"#ef4444"},{label:"WARN",value:status.warn_count,color:"#f59e0b"}].map(m => (
              <div key={m.label} style={{ padding:"6px 8px", borderRadius:"6px",
                background: m.value > 0 ? m.color+"12" : "rgba(255,255,255,0.03)",
                border:`1px solid ${m.value > 0 ? m.color+"30" : "transparent"}` }}>
                <div style={{ fontSize:"16px", fontWeight:800, color: m.value > 0 ? m.color : "#1e293b" }}>{m.value}</div>
                <div style={{ fontSize:"9px", color:"#334155", letterSpacing:"0.8px", fontWeight:700 }}>{m.label}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
