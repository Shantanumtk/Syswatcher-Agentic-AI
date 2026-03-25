import { useEffect, useRef, useState } from "react"
import Head from "next/head"
import ChatWindow    from "../components/ChatWindow"
import StatusBar     from "../components/StatusBar"
import ServerSwitcher from "../components/ServerSwitcher"
import { getServers } from "../lib/api"

export default function Home() {
  const [servers,    setServers]    = useState<string[]>(["local"])
  const [activeServer, setServer]  = useState("local")
  const [threadId,   setThreadId]  = useState("")
  const [tick,       setTick]      = useState(0)

  // Stable thread per server
  const threadMap = useRef<Record<string, string>>({})
  const getThread = (server: string) => {
    if (!threadMap.current[server]) {
      threadMap.current[server] =
        `${server}-${Math.random().toString(36).slice(2, 9)}`
    }
    return threadMap.current[server]
  }

  // Load servers from API
  useEffect(() => {
    getServers().then(s => {
      setServers(s)
      setServer(s[0])
    }).catch(() => {})
  }, [])

  // Update threadId when server changes
  useEffect(() => {
    setThreadId(getThread(activeServer))
  }, [activeServer])

  return (
    <>
      <Head>
        <title>SysWatcher</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </Head>

      <div style={{
        display:       "flex",
        flexDirection: "column",
        height:        "100vh",
        background:    "#13131f",
        color:         "#e0e0f0",
        fontFamily:    "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
      }}>

        {/* Header */}
        <div style={{
          display:      "flex",
          alignItems:   "center",
          padding:      "12px 20px",
          background:   "#1e1e2e",
          borderBottom: "1px solid #2d2d3f",
          gap:          "16px",
        }}>
          {/* Logo */}
          <div style={{
            display:    "flex",
            alignItems: "center",
            gap:        "8px",
          }}>
            <div style={{
              width:        "30px",
              height:       "30px",
              background:   "#4f46e5",
              borderRadius: "8px",
              display:      "flex",
              alignItems:   "center",
              justifyContent: "center",
              fontSize:     "14px",
              fontWeight:   700,
              color:        "white",
            }}>SW</div>
            <span style={{ fontWeight: 700, fontSize: "16px" }}>
              SysWatcher
            </span>
          </div>

          {/* Server switcher */}
          <ServerSwitcher
            servers={servers}
            selected={activeServer}
            onChange={s => setServer(s)}
          />

          {/* Links */}
          <div style={{ marginLeft: "auto", display: "flex", gap: "12px" }}>
            <a
              href={`${process.env.NEXT_PUBLIC_API_URL}/docs`}
              target="_blank"
              rel="noreferrer"
              style={{ color: "#6b6b88", fontSize: "12px", textDecoration: "none" }}
            >
              API docs ↗
            </a>
            <a
              href="http://localhost:3000"
              target="_blank"
              rel="noreferrer"
              style={{ color: "#6b6b88", fontSize: "12px", textDecoration: "none" }}
            >
              Grafana ↗
            </a>
          </div>
        </div>

        {/* Status bar */}
        <StatusBar
          serverName={activeServer}
          onRefresh={() => setTick(t => t + 1)}
        />

        {/* Chat */}
        <div style={{ flex: 1, overflow: "hidden" }}>
          <ChatWindow
            key={activeServer}
            serverName={activeServer}
            threadId={threadId}
          />
        </div>
      </div>
    </>
  )
}
