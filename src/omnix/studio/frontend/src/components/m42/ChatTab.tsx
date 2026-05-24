import { useEffect, useRef, useState } from "react";
import type { ChatMessage } from "./types";

type Props = {
  messages: ChatMessage[];
  onSend: (text: string) => void;
  onAction: (messageId: string, actionId: string) => void;
};

function ts(ms: number) {
  const date = new Date(ms);
  if (Number.isNaN(date.getTime())) return "--:--";
  return date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

export function ChatTab({ messages, onSend, onAction }: Props) {
  const [draft, setDraft] = useState("");
  const logRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const el = logRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [messages]);

  const submit = () => {
    const trimmed = draft.trim();
    if (!trimmed) return;
    onSend(trimmed);
    setDraft("");
  };

  return (
    <div className="m42-chat" data-testid="m42-chat-tab">
      <div className="m42-chat-log" ref={logRef}>
        {messages.length === 0 ? (
          <div className="m42-chat-msg m42-system">
            <span className="m42-chat-msg-meta">agent · {ts(Date.now())}</span>
            <div className="m42-chat-msg-bubble">
              Standing by. Pick a target language in the bottom bar, then choose
              an action below — or type a message.
            </div>
          </div>
        ) : null}
        {messages.map((message) => {
          const role = message.role === "user" ? "m42-self" : message.role === "system" ? "m42-system" : "";
          const label = message.role === "user" ? "you" : message.role === "system" ? "system" : "agent";
          return (
            <div key={message.id} className={`m42-chat-msg ${role}`}>
              <span className="m42-chat-msg-meta">
                {label} · {ts(message.ts)}
              </span>
              <div className="m42-chat-msg-bubble">{message.text}</div>
              {message.actions && message.actions.length > 0 ? (
                <div className="m42-chat-actions">
                  {message.actions.map((action) => (
                    <button
                      key={action.id}
                      type="button"
                      className="m42-chat-action"
                      onClick={() => onAction(message.id, action.id)}
                    >
                      {action.label}
                    </button>
                  ))}
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
      <div className="m42-chat-input-row">
        <input
          type="text"
          className="m42-chat-input"
          placeholder="Message the agent…"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              submit();
            }
          }}
          aria-label="Chat input"
        />
        <button
          type="button"
          className="m42-btn is-primary"
          onClick={submit}
          disabled={draft.trim().length === 0}
        >
          Send
        </button>
      </div>
    </div>
  );
}
