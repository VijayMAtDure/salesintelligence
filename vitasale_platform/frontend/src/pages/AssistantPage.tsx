import { useState, useRef, useEffect } from "react";
import { useSendChatMessage } from "../hooks/useAssistant";

interface DisplayMessage {
  role: "user" | "assistant";
  content: string;
}

/** v1: historical facts (query_metric) + forecasts (get_forecast) only, read-only. See
 * SALES_INTELLIGENCE_AGENT_PLAN.md. Only user/assistant turns are shown — tool-call messages
 * are persisted server-side (for replay as conversation history) but aren't meant for display. */
export function AssistantPage() {
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [input, setInput] = useState("");
  const send = useSendChatMessage();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, send.isPending]);

  const submit = () => {
    const text = input.trim();
    if (!text || send.isPending) return;
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setInput("");
    send.mutate(
      { session_id: sessionId, message: text },
      {
        onSuccess: (resp) => {
          setSessionId(resp.session_id);
          setMessages((prev) => [...prev, { role: "assistant", content: resp.reply }]);
        },
        onError: () => {
          setMessages((prev) => [
            ...prev,
            { role: "assistant", content: "Something went wrong answering that — try again." },
          ]);
        },
      }
    );
  };

  return (
    <div>
      <h1 style={{ fontSize: 20 }}>Assistant</h1>
      <p style={{ color: "#64748b", fontSize: 14 }}>
        Ask about call volume, connect rates, leads, or forecasts — e.g. "what's our busiest hour
        for connected calls" or "how many calls will connect in the next 24 hours."
      </p>

      <div
        style={{
          background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8,
          height: 460, display: "flex", flexDirection: "column",
        }}
      >
        <div style={{ flex: 1, overflowY: "auto", padding: 16 }}>
          {messages.length === 0 && (
            <p style={{ color: "#94a3b8", fontSize: 13 }}>No messages yet — ask something below.</p>
          )}
          {messages.map((m, i) => (
            <div
              key={i}
              style={{
                display: "flex",
                justifyContent: m.role === "user" ? "flex-end" : "flex-start",
                marginBottom: 10,
              }}
            >
              <div
                style={{
                  maxWidth: "75%", padding: "8px 12px", borderRadius: 10, fontSize: 13.5,
                  lineHeight: 1.5,
                  background: m.role === "user" ? "#0f172a" : "#f1f5f9",
                  color: m.role === "user" ? "#fff" : "#0f172a",
                }}
              >
                {m.content}
              </div>
            </div>
          ))}
          {send.isPending && (
            <div style={{ display: "flex", justifyContent: "flex-start", marginBottom: 10 }}>
              <div style={{ padding: "8px 12px", borderRadius: 10, background: "#f1f5f9", fontSize: 13, color: "#94a3b8" }}>
                Thinking…
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <div style={{ borderTop: "1px solid #e2e8f0", padding: 10, display: "flex", gap: 8 }}>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit()}
            placeholder="Ask a question…"
            style={{
              flex: 1, padding: "8px 10px", borderRadius: 6, border: "1px solid #cbd5e1",
              fontSize: 13.5, outline: "none",
            }}
          />
          <button
            onClick={submit}
            disabled={send.isPending || !input.trim()}
            style={{
              padding: "8px 16px", borderRadius: 6, border: "none", fontSize: 13.5,
              fontWeight: 600, color: "#fff",
              background: send.isPending || !input.trim() ? "#94a3b8" : "#0f172a",
              cursor: send.isPending || !input.trim() ? "default" : "pointer",
            }}
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}
