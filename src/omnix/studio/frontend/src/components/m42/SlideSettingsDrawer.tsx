import type { ReactNode } from "react";
import { useEffect } from "react";

type Section = {
  id: string;
  label: string;
  render: () => ReactNode;
};

type Props = {
  open: boolean;
  onClose: () => void;
  sections: Section[];
  active: string;
  onActiveChange: (id: string) => void;
};

export function SlideSettingsDrawer({ open, onClose, sections, active, onActiveChange }: Props) {
  useEffect(() => {
    if (!open) return;
    const esc = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [onClose, open]);

  const activeSection = sections.find((section) => section.id === active) ?? sections[0];

  return (
    <>
      <div
        className={`m42-slidedrawer-overlay ${open ? "is-open" : ""}`}
        onClick={onClose}
        aria-hidden
      />
      <aside
        className={`m42-slidedrawer ${open ? "is-open" : ""}`}
        aria-label="Settings"
        aria-hidden={!open}
      >
        <div className="m42-slidedrawer-head">
          <span>Settings</span>
          <button
            type="button"
            className="m42-iconbtn"
            onClick={onClose}
            aria-label="Close settings"
          >
            ✕
          </button>
        </div>
        <nav
          style={{
            display: "flex",
            gap: 1,
            padding: "0 12px",
            borderBottom: "0.5px solid var(--m42-border)",
            background: "var(--m42-bg-1)",
          }}
          role="tablist"
          aria-label="Settings sections"
        >
          {sections.map((section) => (
            <button
              key={section.id}
              type="button"
              role="tab"
              aria-selected={section.id === active}
              className={`m42-tab ${section.id === active ? "is-active" : ""}`}
              style={{ flex: "0 0 auto", padding: "0 10px" }}
              onClick={() => onActiveChange(section.id)}
            >
              {section.label}
            </button>
          ))}
        </nav>
        <div className="m42-slidedrawer-body">{activeSection?.render() ?? null}</div>
      </aside>
    </>
  );
}
