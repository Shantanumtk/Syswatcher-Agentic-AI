const getApiUrl = (): string => {
  if (typeof window !== "undefined") {
    return `http://${window.location.hostname}:8000`
  }
  return "http://localhost:8000"
}
const API = getApiUrl()

export interface AskResponse {
  answer:    string
  severity:  string
  thread_id: string
  server:    string
}

export interface StatusResponse {
  overall:           string
  critical_count:    number
  warn_count:        number
  info_count:        number
  total_events:      number
  period_hours:      number
  last_sweep_at:     string | null
  last_sweep_status: string | null
  servers:           string[]
  database:          string
}

export interface Message {
  id:        string
  role:      "user" | "agent"
  content:   string
  severity?: string
  ts:        Date
}

export async function askAgent(
  question:   string,
  threadId:   string,
  serverName: string
): Promise<AskResponse> {
  const res = await fetch(`${API}/ask`, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify({
      question,
      thread_id:   threadId,
      server_name: serverName,
    }),
  })
  if (!res.ok) throw new Error(`Ask failed: ${res.status}`)
  return res.json()
}

export async function getStatus(serverName?: string): Promise<StatusResponse> {
  const params = serverName ? `?server_name=${serverName}` : ""
  const res = await fetch(`${API}/status${params}`)
  if (!res.ok) throw new Error(`Status failed: ${res.status}`)
  return res.json()
}

export async function getServers(): Promise<string[]> {
  const res = await fetch(`${API}/servers`)
  if (!res.ok) return ["local"]
  const data = await res.json()
  const names: string[] = (data.servers || []).map((s: { name: string }) => s.name)
  return names.length > 0 ? names : ["local"]
}

export async function runSweep(serverName: string): Promise<{ report: string; severity: string }> {
  const res = await fetch(`${API}/sweep`, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify({ server_name: serverName }),
  })
  if (!res.ok) throw new Error(`Sweep failed: ${res.status}`)
  return res.json()
}
