import { useEffect, useRef, useState } from "react";

type ConnectionStatus = "connected" | "connecting" | "closed";

type WorkspaceOption = {
  id: string;
  label: string;
  path: string;
};

type Props = {
  workspaceLabel: string;
  workspacePath: string;
  workspaces?: WorkspaceOption[];
  onSelectWorkspace?: (id: string) => void;
  indexedCommit?: string;
  status: ConnectionStatus;
  model: string;
  onChangeModel: (model: string) => void;
  models?: string[];
  onOpenSettings: () => void;
  onOpenPalette?: () => void;
  userInitial?: string;
};

const DEFAULT_MODELS = [
  "Opus 4.7",
  "Sonnet 4.6",
  "Haiku 4.5",
  "Local (no model)",
];

function dotClass(status: ConnectionStatus): string {
  if (status === "connected") return "m42-pill-dot";
  if (status === "connecting") return "m42-pill-dot is-warn";
  return "m42-pill-dot is-err";
}

function statusLabel(status: ConnectionStatus): string {
  if (status === "connected") return "connected";
  if (status === "connecting") return "connecting…";
  return "offline";
}

export function TopBar({
  workspaceLabel,
  workspacePath,
  workspaces,
  onSelectWorkspace,
  indexedCommit,
  status,
  model,
  onChangeModel,
  models = DEFAULT_MODELS,
  onOpenSettings,
  onOpenPalette,
  userInitial = "H",
}: Props) {
  const [wsOpen, setWsOpen] = useState(false);
  const [modelOpen, setModelOpen] = useState(false);
  const wsRef = useRef<HTMLDivElement | null>(null);
  const modelRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!wsOpen && !modelOpen) return;
    const close = (event: MouseEvent) => {
      if (wsRef.current && !wsRef.current.contains(event.target as Node)) {
        setWsOpen(false);
      }
      if (modelRef.current && !modelRef.current.contains(event.target as Node)) {
        setModelOpen(false);
      }
    };
    const esc = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setWsOpen(false);
        setModelOpen(false);
      }
    };
    window.addEventListener("mousedown", close);
    window.addEventListener("keydown", esc);
    return () => {
      window.removeEventListener("mousedown", close);
      window.removeEventListener("keydown", esc);
    };
  }, [wsOpen, modelOpen]);

  return (
    <header className="m42-topbar" data-testid="m42-topbar">
      <span className="m42-topbar-wordmark">OMNIX</span>
      <span className="m42-topbar-sep">/</span>
      <div className="m42-dropdown" ref={wsRef}>
        <button
          type="button"
          className="m42-iconbtn"
          aria-haspopup="menu"
          aria-expanded={wsOpen}
          onClick={() => setWsOpen((s) => !s)}
          title={workspacePath}
        >
          <span style={{ fontSize: 12 }}>{workspaceLabel}</span>
          <span className="m42-dropdown-caret" style={{ marginLeft: 6 }}>
            ▾
          </span>
        </button>
        {wsOpen && workspaces && workspaces.length > 0 ? (
          <div className="m42-dropdown-menu m42-anchor-top" role="menu">
            {workspaces.map((workspace) => (
              <button
                key={workspace.id}
                type="button"
                role="menuitem"
                className="m42-dropdown-item"
                onClick={() => {
                  setWsOpen(false);
                  onSelectWorkspace?.(workspace.id);
                }}
              >
                <span>{workspace.label}</span>
                <span className="m42-dropdown-item-hint">{workspace.path}</span>
              </button>
            ))}
          </div>
        ) : null}
      </div>
      <span className="m42-topbar-sep" style={{ marginLeft: -2 }}>
        ·
      </span>
      <span
        className="m42-topbar-sep"
        style={{ fontFamily: "var(--omnix-font-mono)", fontSize: 11 }}
        title={workspacePath}
      >
        {workspacePath}
      </span>

      <div className="m42-topbar-right">
        {onOpenPalette ? (
          <button
            type="button"
            className="m42-iconbtn"
            onClick={onOpenPalette}
            title="Command palette (⌘K)"
            aria-label="Command palette"
          >
            <span style={{ fontFamily: "var(--omnix-font-mono)", fontSize: 11 }}>⌘K</span>
          </button>
        ) : null}
        <span className="m42-topbar-pill" data-testid="m42-conn-pill">
          <span className={dotClass(status)} aria-hidden />
          <span>{statusLabel(status)}</span>
        </span>
        {indexedCommit ? (
          <span
            className="m42-topbar-pill"
            title="Indexed commit"
            data-testid="m42-commit-pill"
          >
            <span style={{ color: "var(--m42-text-tertiary)" }}>idx</span>
            <span>{indexedCommit.slice(0, 7)}</span>
          </span>
        ) : null}
        <div className="m42-dropdown" ref={modelRef}>
          <button
            type="button"
            className="m42-iconbtn"
            aria-haspopup="menu"
            aria-expanded={modelOpen}
            onClick={() => setModelOpen((s) => !s)}
          >
            <span style={{ fontFamily: "var(--omnix-font-mono)", fontSize: 11 }}>
              {model}
            </span>
            <span className="m42-dropdown-caret" style={{ marginLeft: 6 }}>
              ▾
            </span>
          </button>
          {modelOpen ? (
            <div className="m42-dropdown-menu m42-anchor-right m42-anchor-top" role="menu">
              {models.map((option) => (
                <button
                  key={option}
                  type="button"
                  role="menuitem"
                  className={`m42-dropdown-item ${option === model ? "is-active" : ""}`}
                  onClick={() => {
                    setModelOpen(false);
                    onChangeModel(option);
                  }}
                >
                  <span>{option}</span>
                </button>
              ))}
            </div>
          ) : null}
        </div>
        <button
          type="button"
          className="m42-iconbtn"
          onClick={onOpenSettings}
          aria-label="Settings"
          title="Settings"
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            aria-hidden
          >
            <circle cx="12" cy="12" r="3" />
            <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1A2 2 0 1 1 4.1 16.7l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.6-1.1 1.7 1.7 0 0 0-.3-1.9l-.1-.1A2 2 0 1 1 7.1 4.7l.1.1a1.7 1.7 0 0 0 1.9.3H9.1a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" />
          </svg>
        </button>
        <span className="m42-avatar" aria-label="User">
          {userInitial}
        </span>
      </div>
    </header>
  );
}
