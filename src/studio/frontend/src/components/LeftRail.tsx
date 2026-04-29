import type { ReactNode } from "react";

export type LeftRailDrawer = "files" | "search" | "bugs" | "receipts" | "settings";

const IcoFiles = (props: { className?: string }) => (
  <svg
    className={props.className}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    aria-hidden
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M3 7.5A2.25 2.25 0 015.25 5.25h4.379a2.25 2.25 0 011.59.659l.53.53M3 7.5V18a2.25 2.25 0 002.25 2.25h6.75A2.25 2.25 0 0016.5 18v-4.5M3 7.5h12.75M12.75 7.5V5.25A2.25 2.25 0 0115 3h1.5a2.25 2.25 0 012.25 2.25V7.5"
    />
  </svg>
);

const IcoSearch = (props: { className?: string }) => (
  <svg
    className={props.className}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    aria-hidden
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M21 21l-4.35-4.35m0 0A7.5 7.5 0 1010.5 19a7.5 7.5 0 0012.15-2.35z"
    />
  </svg>
);

const IcoBug = (props: { className?: string }) => (
  <svg
    className={props.className}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    aria-hidden
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M9 9.75h6M9 13.5h6M7.5 6.75l-2-2m11 2 2-2M6.75 12H4m16 0h-2.75M7.5 17.25l-2 2m11-2 2 2M8 7.5A4 4 0 0112 5a4 4 0 014 2.5v7A4 4 0 0112 18.5a4 4 0 01-4-4v-7z"
    />
  </svg>
);

const IcoReceipt = (props: { className?: string }) => (
  <svg
    className={props.className}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    aria-hidden
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M7.5 3.75h9A1.5 1.5 0 0118 5.25v15l-3-1.5-3 1.5-3-1.5-3 1.5v-15a1.5 1.5 0 011.5-1.5zM9 8.25h6M9 11.25h6M9 14.25h3.75"
    />
  </svg>
);

const IcoCog = (props: { className?: string }) => (
  <svg
    className={props.className}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    aria-hidden
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.375.3.67.6.8.3.13.64.1.9-.1l1.1-.8a1.1 1.1 0 011.3.1l1.8 1.8a1.1 1.1 0 01.1 1.3l-.8 1.1a.8.8 0 00-.1.9c.13.3.425.54.8.6l1.28.2c.54.09.94.56.94 1.11v2.59c0 .55-.4 1.02-.94 1.1l-1.28.21a.8.8 0 00-.8.6c-.14.3-.1.64.1.9l.8 1.1a1.1 1.1 0 01-.1 1.3l-1.8 1.8a1.1 1.1 0 01-1.3.1l-1.1-.8a.8.8 0 00-.9-.1.9.8 0 00-.6.6l-.21 1.28a1.05 1.05 0 01-1.1.95h-2.59a1.05 1.05 0 01-1.1-.95l-.2-1.28a.8.8 0 00-.6-.6.9.8 0 00-.9.1l-1.1.8a1.1 1.1 0 01-1.3-.1l-1.8-1.8a1.1 1.1 0 01-.1-1.3l.8-1.1a.8.8 0 00.1-.9.9.8 0 00-.6-.6l-1.28-.21A1.05 1.05 0 013 19.2v-2.59a1.05 1.05 0 01.95-1.1l1.28-.2a.8.8 0 00.6-.8.8.8 0 00-.1-.9l-.8-1.1A1.1 1.1 0 013 9.1l1.8-1.8a1.1 1.1 0 011.3-.1l1.1.8a.8.8 0 00.9.1.9.8 0 00.6-.6L9.2 3.1zM12 15.75A3.75 3.75 0 1112 8.25a3.75 3.75 0 010 7.5z"
    />
  </svg>
);

type Props = {
  active: LeftRailDrawer | null;
  onSelect: (drawer: LeftRailDrawer) => void;
  onClose: () => void;
  children?: ReactNode;
};

const railBtn =
  "omnix-rail-btn flex h-12 w-full cursor-pointer items-center justify-center border-0 bg-transparent p-0 transition-colors text-omnix-text-muted hover:bg-[rgba(255,255,255,0.04)] hover:text-omnix-text-primary";

const items: Array<{
  id: LeftRailDrawer;
  label: string;
  icon: (props: { className?: string }) => JSX.Element;
}> = [
  { id: "files", label: "Files", icon: IcoFiles },
  { id: "search", label: "Search", icon: IcoSearch },
  { id: "bugs", label: "Bugs", icon: IcoBug },
  { id: "receipts", label: "Receipts", icon: IcoReceipt },
  { id: "settings", label: "Settings", icon: IcoCog },
];

export function LeftRail({ active, onSelect, onClose, children }: Props) {
  return (
    <>
      <nav className="omnix-left-rail" aria-label="OMNIX activity">
        {items.map((item) => {
          const Icon = item.icon;
          const selected = active === item.id;
          return (
            <button
              key={item.id}
              type="button"
              className={`${railBtn} ${selected ? "is-active" : ""}`}
              title={item.label}
              aria-label={item.label}
              aria-pressed={selected}
              onClick={() => {
                if (selected) onClose();
                else onSelect(item.id);
              }}
            >
              <Icon className="h-6 w-6" />
            </button>
          );
        })}
      </nav>
      <aside
        className={`omnix-left-drawer ${active ? "is-open" : ""}`}
        aria-label={active ? `${active} drawer` : "OMNIX drawer"}
        aria-hidden={active ? "false" : "true"}
      >
        <div className="flex items-center justify-between border-b border-[var(--omnix-shell-border)] px-3 py-2.5">
          <div className="font-display text-xs font-bold uppercase tracking-[0.22em] text-omnix-text-primary">
            {active ?? "OMNIX"}
          </div>
          <button
            type="button"
            className="h-7 w-7 rounded border border-[var(--omnix-shell-border)] bg-transparent text-omnix-text-muted hover:text-omnix-text-primary"
            onClick={onClose}
            aria-label="Close drawer"
          >
            x
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-auto">{children}</div>
      </aside>
    </>
  );
}
