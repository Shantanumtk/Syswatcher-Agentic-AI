interface Props { onSelect: (prompt: string) => void }

const PROMPTS = [
  { category:"HEALTH", icon:"◈", color:"#10b981", items:[
    {label:"Full health check", prompt:"Is everything ok?"},
    {label:"Run full sweep", prompt:"Run a full sweep"},
    {label:"CPU status", prompt:"What's the CPU usage?"},
    {label:"Memory status", prompt:"What's the memory usage?"},
    {label:"Disk usage", prompt:"Show disk usage"},
    {label:"Network stats", prompt:"Show network statistics"},
    {label:"Load average", prompt:"What's the load average?"},
    {label:"System uptime", prompt:"How long has the server been running?"},
  ]},
  { category:"PROCESSES", icon:"⬡", color:"#6366f1", items:[
    {label:"Top processes", prompt:"What are the top processes by CPU?"},
    {label:"Zombie processes", prompt:"Are there any zombie processes?"},
    {label:"Open ports", prompt:"What ports are open?"},
    {label:"Auth failures", prompt:"Any auth failures in the last 24 hours?"},
  ]},
  { category:"CRONS", icon:"◷", color:"#f59e0b", items:[
    {label:"List all crons", prompt:"Show all cron jobs"},
    {label:"Recent cron logs", prompt:"Show recent cron logs"},
    {label:"Failed crons", prompt:"Did any cron jobs fail?"},
    {label:"Create cron", prompt:"Create a cron job every day at 2am called daily_backup that runs /opt/scripts/backup.sh and logs to /var/log/backup.log"},
  ]},
  { category:"ALERTS", icon:"◉", color:"#ef4444", items:[
    {label:"List alert rules", prompt:"Show all alert rules"},
    {label:"CPU alert 80%", prompt:"Add an alert if CPU goes above 80% with slack notification"},
    {label:"Disk alert 85%", prompt:"Add an alert if disk goes above 85% with slack notification"},
    {label:"Memory alert 90%", prompt:"Add an alert if memory goes above 90% with slack notification"},
  ]},
  { category:"NOTIFICATIONS", icon:"◎", color:"#06b6d4", items:[
    {label:"Send Slack alert", prompt:"Send a slack alert that all systems are healthy"},
    {label:"Prometheus alerts", prompt:"Are there any Prometheus alerts firing?"},
  ]},
  { category:"LOGS", icon:"≡", color:"#8b5cf6", items:[
    {label:"Tail syslog", prompt:"Show last 50 lines of /var/log/syslog"},
    {label:"Search errors", prompt:"Search for ERROR in /var/log/syslog"},
    {label:"Auth log failures", prompt:"Show authentication failures from auth logs"},
  ]},
]

export default function PromptsPanel({ onSelect }: Props) {
  return (
    <div style={{ width:"260px", flexShrink:0, borderLeft:"1px solid rgba(255,255,255,0.05)",
      background:"rgba(6,6,10,0.98)", display:"flex", flexDirection:"column", overflowY:"auto",
      scrollbarWidth:"thin", scrollbarColor:"rgba(255,255,255,0.06) transparent" }}>
      <div style={{ padding:"14px 16px 10px", borderBottom:"1px solid rgba(255,255,255,0.05)",
        position:"sticky", top:0, background:"rgba(6,6,10,0.98)", backdropFilter:"blur(8px)", zIndex:1 }}>
        <div style={{ fontSize:"11px", fontWeight:700, color:"#6366f1", letterSpacing:"2px" }}>⌘ COMMAND LIBRARY</div>
        <div style={{ fontSize:"11px", color:"#334155", marginTop:"2px", fontFamily:"'JetBrains Mono',monospace" }}>Click to insert prompt</div>
      </div>
      <div style={{ padding:"8px 0" }}>
        {PROMPTS.map(cat => (
          <div key={cat.category} style={{ marginBottom:"4px" }}>
            <div style={{ display:"flex", alignItems:"center", gap:"6px", padding:"6px 16px 4px" }}>
              <span style={{ color:cat.color, fontSize:"12px" }}>{cat.icon}</span>
              <span style={{ fontSize:"9px", fontWeight:700, color:"#334155", letterSpacing:"1.5px" }}>{cat.category}</span>
            </div>
            {cat.items.map(item => (
              <button key={item.label} onClick={() => onSelect(item.prompt)} style={{
                width:"100%", textAlign:"left", padding:"6px 16px 6px 28px",
                background:"transparent", border:"none", cursor:"pointer",
                color:"#64748b", fontSize:"12px", fontFamily:"'JetBrains Mono',monospace", display:"block" }}
                onMouseEnter={e => { const el = e.currentTarget; el.style.background=cat.color+"10"; el.style.color=cat.color }}
                onMouseLeave={e => { const el = e.currentTarget; el.style.background="transparent"; el.style.color="#64748b" }}>
                › {item.label}
              </button>
            ))}
          </div>
        ))}
      </div>
      <div style={{ padding:"12px 16px", marginTop:"auto", borderTop:"1px solid rgba(255,255,255,0.04)",
        fontSize:"10px", color:"#1e293b", fontFamily:"'JetBrains Mono',monospace", lineHeight:"1.6" }}>
        Ask anything in plain English — the AI picks the right tools.
      </div>
    </div>
  )
}
