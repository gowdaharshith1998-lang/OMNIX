const IcoFolder = (props: { className?: string }) => (
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

type Active = "project" | "find" | "settings" | null;

type Props = {
  projectPath: string;
  active: Active;
  onProjectInfo?: () => void;
  onOpenFind: () => void;
  onOpenSettings: () => void;
  /** Project icon: e.g. copy path or return to open-folder flow. */
  onProject?: () => void;
};

const railBtn =
  "sb-rail-btn flex h-12 w-full cursor-pointer items-center justify-center border-0 bg-transparent p-0 transition-transform duration-150 text-[--omnix-sb-muted] hover:bg-[--omnix-sb-glow] hover:text-[--omnix-sb-text] rounded-sm mx-0.5";

export function LeftIconStrip({
  projectPath,
  active,
  onOpenFind,
  onOpenSettings,
  onProject,
}: Props) {
  return (
    <nav
      className="fixed left-0 top-0 z-[45] box-border flex h-full w-12 min-w-12 flex-col border-r border-[--omnix-sb-border] bg-[--omnix-sb-bg] py-1.5 pb-2.5 will-change-transform"
      aria-label="OMNIX activity"
    >
      <button
        type="button"
        className={`${railBtn} ${
          active === "project"
            ? "text-[--omnix-sb-accent] [box-shadow:inset_2px_0_0_0_var(--omnix-sb-accent)]"
            : ""
        }`}
        title={projectPath || "Project path"}
        aria-label="Project"
        onClick={() => onProject?.()}
      >
        <IcoFolder className="sb-ico h-6 w-6" />
      </button>
      <button
        type="button"
        className={`${railBtn} ${
          active === "find"
            ? "text-[--omnix-sb-accent] [box-shadow:inset_2px_0_0_0_var(--omnix-sb-accent)]"
            : ""
        }`}
        title="Quick open (Cmd+P)"
        aria-label="Find file"
        aria-pressed={active === "find"}
        onClick={onOpenFind}
      >
        <IcoSearch className="sb-ico h-6 w-6" />
      </button>

      <div className="mt-auto flex flex-col">
        <button
          type="button"
          className={`${railBtn} ${
            active === "settings"
              ? "text-[--omnix-sb-accent] [box-shadow:inset_2px_0_0_0_var(--omnix-sb-accent)]"
              : ""
          }`}
          title="Settings"
          aria-label="Settings"
          aria-pressed={active === "settings"}
          onClick={onOpenSettings}
        >
          <IcoCog className="sb-ico h-6 w-6" />
        </button>
      </div>
    </nav>
  );
}
