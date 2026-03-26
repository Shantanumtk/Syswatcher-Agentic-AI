import { useEffect, useRef, useState } from "react"
import Head from "next/head"
import { getServers, getStatus, StatusResponse } from "../lib/api"
import ChatPanel from "../components/ChatPanel"
import Sidebar from "../components/Sidebar"
import PromptsPanel from "../components/PromptsPanel"

export default function Home() {
  const [servers, setServers] = useState<string[]>(["local"])
  const [activeServer, setServer] = useState("local")
  const [status, setStatus] = useState<StatusResponse | null>(null)
  const [showPrompts, setShowPrompts] = useState(false)
  const [chatHistory, setChatHistory] = useState<{id:string; server:string; preview:string; ts:Date}[]>([])
  const [activeChat, setActiveChat] = useState<string>("default")
  const threadMap = useRef<Record<string,string>>({})

  const getThread = (server: string) => {
    if (!threadMap.current[server]) {
      threadMap.current[server] = `${server}-${Math.random().toString(36).slice(2,9)}`
    }
    return threadMap.current[server]
  }

  useEffect(() => {
    getServers().then(s => { setServers(s); setServer(s[0]) }).catch(()=>{})
  }, [])

  useEffect(() => {
    const fetchStatus = () => getStatus(activeServer, 5).then(setStatus).catch(()=>{})
    fetchStatus()
    const id = setInterval(fetchStatus, 15000)
    return () => clearInterval(id)
  }, [activeServer])

  const addToHistory = (server: string, preview: string) => {
    const id = Date.now().toString()
    setChatHistory(prev => [{id, server, preview, ts: new Date()}, ...prev.slice(0,19)])
  }

  return (
    <>
      <Head>
        <title>SysWatcher — AI Infrastructure Monitor</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;700&family=Syne:wght@400;600;700;800&display=swap" rel="stylesheet" />
      </Head>

      <div style={{
        display: "flex", height: "100vh", background: "#050508",
        color: "#e2e8f0", fontFamily: "\'Syne\', sans-serif", overflow: "hidden",
      }}>
        <div style={{
          position: "fixed", inset: 0, pointerEvents: "none", zIndex: 0,
          background: `radial-gradient(ellipse 80% 50% at 20% 0%, rgba(99,102,241,0.08) 0%, transparent 60%),
            radial-gradient(ellipse 60% 40% at 80% 100%, rgba(16,185,129,0.05) 0%, transparent 60%)`
        }} />

        <Sidebar
          servers={servers}
          activeServer={activeServer}
          onServerChange={setServer}
          chatHistory={chatHistory}
          activeChat={activeChat}
          onChatSelect={setActiveChat}
          status={status}
        />

        <div style={{ flex: 1, display: "flex", flexDirection: "column", position: "relative", zIndex: 1, minWidth: 0 }}>
          <TopBar
            activeServer={activeServer}
            status={status}
            showPrompts={showPrompts}
            onTogglePrompts={() => setShowPrompts(p => !p)}
          />
          <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
            <ChatPanel
              key={activeServer}
              serverName={activeServer}
              threadId={getThread(activeServer)}
              onMessage={addToHistory}
            />
            {showPrompts && (
              <PromptsPanel onSelect={(p) => {
                window.dispatchEvent(new CustomEvent("syswatcher:prompt", { detail: p }))
                setShowPrompts(false)
              }} />
            )}
          </div>
        </div>
      </div>
    </>
  )
}

function TopBar({ activeServer, status, showPrompts, onTogglePrompts }: {
  activeServer: string
  status: StatusResponse | null
  showPrompts: boolean
  onTogglePrompts: () => void
}) {
  const overall = status?.overall || "healthy"
  const colors = { healthy: "#10b981", warn: "#f59e0b", critical: "#ef4444" }
  const color = colors[overall as keyof typeof colors] || colors.healthy

  return (
    <div style={{
      display: "flex", alignItems: "center", gap: "16px",
      padding: "0 20px", height: "52px",
      borderBottom: "1px solid rgba(255,255,255,0.05)",
      background: "rgba(5,5,8,0.8)", backdropFilter: "blur(12px)", flexShrink: 0,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
        <div style={{
          width: "6px", height: "6px", borderRadius: "50%", background: color,
          boxShadow: `0 0 8px ${color}`,
          animation: overall === "critical" ? "swpulse 1s infinite" : "none",
        }} />
        <span style={{ fontFamily: "\'JetBrains Mono\', monospace", fontSize: "13px", color: "#94a3b8" }}>
          {activeServer}
        </span>
        <span style={{
          padding: "2px 8px", borderRadius: "4px", fontSize: "11px", fontWeight: 600,
          background: color + "20", color, border: `1px solid ${color}40`,
          fontFamily: "\'JetBrains Mono\', monospace",
        }}>
          {overall.toUpperCase()}
        </span>
      </div>

      {status && (
        <div style={{ display: "flex", gap: "16px", marginLeft: "8px" }}>
          {status.critical_count > 0 && (
            <span style={{ fontSize: "12px", color: "#ef4444", fontFamily: "\'JetBrains Mono\', monospace" }}>
              ⚠ {status.critical_count} critical
            </span>
          )}
          {status.warn_count > 0 && (
            <span style={{ fontSize: "12px", color: "#f59e0b", fontFamily: "\'JetBrains Mono\', monospace" }}>
              △ {status.warn_count} warn
            </span>
          )}
          {status.last_sweep_at && (
            <span style={{ fontSize: "11px", color: "#475569", fontFamily: "\'JetBrains Mono\', monospace" }}>
              sweep: {new Date(status.last_sweep_at).toLocaleTimeString()}
            </span>
          )}
        </div>
      )}

      <div style={{ marginLeft: "auto", display: "flex", gap: "8px", alignItems: "center" }}>
        <button onClick={onTogglePrompts} style={{
          display: "flex", alignItems: "center", gap: "6px",
          padding: "6px 12px", borderRadius: "6px", border: "none", cursor: "pointer",
          background: showPrompts ? "rgba(99,102,241,0.2)" : "rgba(255,255,255,0.05)",
          color: showPrompts ? "#818cf8" : "#64748b",
          fontSize: "12px", fontWeight: 600, fontFamily: "\'Syne\', sans-serif",
        }}>
          ⌘ Commands
        </button>
        <a href="http://localhost:3000" target="_blank" rel="noreferrer" style={{
          padding: "6px 12px", borderRadius: "6px", background: "rgba(255,255,255,0.05)",
          color: "#64748b", fontSize: "12px", textDecoration: "none", fontWeight: 600,
        }}>Grafana ↗</a>
        <a href={`${typeof window !== "undefined" ? `http://${window.location.hostname}:8000` : ""}/docs`}
          target="_blank" rel="noreferrer" style={{
          padding: "6px 12px", borderRadius: "6px", background: "rgba(255,255,255,0.05)",
          color: "#64748b", fontSize: "12px", textDecoration: "none", fontWeight: 600,
        }}>API ↗</a>
      </div>
      <style>{`@keyframes swpulse { 0%,100%{opacity:1} 50%{opacity:0.4} }`}</style>
    </div>
  )
}
