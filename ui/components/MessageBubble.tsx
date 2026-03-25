import { Message } from "../lib/api"

interface Props { message: Message }

const SEV_COLOR: Record<string, string> = {
  critical: "#ef4444",
  warn:     "#f59e0b",
  healthy:  "#22c55e",
}

export default function MessageBubble({ message }: Props) {
  const isUser = message.role === "user"

  return (
    <div style={{
      display:       "flex",
      justifyContent: isUser ? "flex-end" : "flex-start",
      marginBottom:  "12px",
    }}>
      {/* Agent avatar */}
      {!isUser && (
        <div style={{
          width:        "28px",
          height:       "28px",
          borderRadius: "50%",
          background:   "#4f46e5",
          display:      "flex",
          alignItems:   "center",
          justifyContent: "center",
          fontSize:     "12px",
          color:        "white",
          flexShrink:   0,
          marginRight:  "8px",
          marginTop:    "2px",
        }}>SW</div>
      )}

      <div style={{ maxWidth: "75%" }}>
        {/* Severity badge for agent messages */}
        {!isUser && message.severity && message.severity !== "healthy" && (
          <div style={{
            display:      "inline-block",
            background:   SEV_COLOR[message.severity] + "22",
            color:        SEV_COLOR[message.severity],
            border:       `1px solid ${SEV_COLOR[message.severity]}44`,
            borderRadius: "4px",
            padding:      "1px 8px",
            fontSize:     "11px",
            fontWeight:   600,
            marginBottom: "4px",
          }}>
            {message.severity.toUpperCase()}
          </div>
        )}

        {/* Bubble */}
        <div style={{
          background:   isUser ? "#4f46e5" : "#2d2d3f",
          color:        "#e0e0f0",
          padding:      "10px 14px",
          borderRadius: isUser
            ? "18px 18px 4px 18px"
            : "18px 18px 18px 4px",
          fontSize:     "14px",
          lineHeight:   "1.6",
          whiteSpace:   "pre-wrap",
          wordBreak:    "break-word",
        }}>
          {message.content}
        </div>

        {/* Timestamp */}
        <div style={{
          fontSize:  "11px",
          color:     "#4a4a68",
          marginTop: "3px",
          textAlign: isUser ? "right" : "left",
        }}>
          {message.ts.toLocaleTimeString()}
        </div>
      </div>
    </div>
  )
}
