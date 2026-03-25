import { useEffect, useState } from "react"
import { getStatus, StatusResponse } from "../lib/api"

interface Props {
  serverName: string
  onRefresh?: () => void
}

const DOT: Record<string, string> = {
  healthy:  "#22c55e",
  warn:     "#f59e0b",
  critical: "#ef4444",
  unknown:  "#6b7280",
}

const LABEL: Record<string, string> = {
  healthy:  "Healthy",
  warn:     "Warning",
  critical: "Critical",
  unknown:  "Unknown",
}

export default function StatusBar({ serverName, onRefresh }: Props) {
  const [status, setStatus] = useState<StatusResponse | null>(null)
  const [loading, setLoading] = useState(true)

  const fetch_ = async () => {
    try {
      const s = await getStatus(serverName)
      setStatus(s)
    } catch {
      /* keep stale data */
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetch_()
    const id = setInterval(fetch_, 30_000)   // poll every 30s
    return () => clearInterval(id)
  }, [serverName])

  const overall = status?.overall || "unknown"
  const color   = DOT[overall] || DOT.unknown

  const lastSweep = status?.last_sweep_at
    ? new Date(status.last_sweep_at).toLocaleTimeString()
    : "never"

  return (
    <div style={{
      display:         "flex",
      alignItems:      "center",
      gap:             "16px",
      padding:         "10px 20px",
      background:      "#1e1e2e",
      borderBottom:    "1px solid #2d2d3f",
      fontSize:        "13px",
      color:           "#a0a0b8",
      flexWrap:        "wrap",
    }}>
      {/* Status dot + label */}
      <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
        <span style={{
          width:        "8px",
          height:       "8px",
          borderRadius: "50%",
          background:   color,
          display:      "inline-block",
          flexShrink:   0,
        }} />
        <span style={{ color, fontWeight: 600 }}>
          {loading ? "Checking…" : LABEL[overall]}
        </span>
      </div>

      {/* Server */}
      <span style={{ color: "#6b6b88" }}>|</span>
      <span>
        <span style={{ color: "#6b6b88" }}>server: </span>
        <span style={{ color: "#e0e0f0" }}>{serverName}</span>
      </span>

      {/* Event counts */}
      {status && (
        <>
          <span style={{ color: "#6b6b88" }}>|</span>
          {status.critical_count > 0 && (
            <span style={{ color: "#ef4444" }}>
              {status.critical_count} critical
            </span>
          )}
          {status.warn_count > 0 && (
            <span style={{ color: "#f59e0b" }}>
              {status.warn_count} warn
            </span>
          )}
          {status.critical_count === 0 && status.warn_count === 0 && (
            <span style={{ color: "#22c55e" }}>no issues</span>
          )}
        </>
      )}

      {/* Last sweep */}
      <span style={{ color: "#6b6b88" }}>|</span>
      <span>
        <span style={{ color: "#6b6b88" }}>last sweep: </span>
        <span style={{ color: "#e0e0f0" }}>{lastSweep}</span>
      </span>

      {/* Manual refresh */}
      <button
        onClick={() => { fetch_(); onRefresh?.() }}
        style={{
          marginLeft:    "auto",
          background:    "transparent",
          border:        "1px solid #3d3d5c",
          color:         "#a0a0b8",
          padding:       "3px 10px",
          borderRadius:  "4px",
          cursor:        "pointer",
          fontSize:      "12px",
        }}
      >
        ↻ refresh
      </button>
    </div>
  )
}
