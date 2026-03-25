interface Props {
  servers:  string[]
  selected: string
  onChange: (server: string) => void
}

export default function ServerSwitcher({ servers, selected, onChange }: Props) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
      <span style={{ fontSize: "12px", color: "#6b6b88" }}>Server:</span>
      <select
        value={selected}
        onChange={e => onChange(e.target.value)}
        style={{
          background:   "#2d2d3f",
          border:       "1px solid #3d3d5c",
          color:        "#e0e0f0",
          padding:      "4px 8px",
          borderRadius: "4px",
          fontSize:     "13px",
          cursor:       "pointer",
        }}
      >
        {servers.map(s => (
          <option key={s} value={s}>{s}</option>
        ))}
      </select>
    </div>
  )
}
