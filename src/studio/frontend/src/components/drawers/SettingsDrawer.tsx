import { useMemo, useState } from "react";

const providers = ["Anthropic", "OpenAI", "Google", "Ollama"];

type KeyDraft = {
  provider: string;
  label: string;
};

type Props = {
  projectPath: string;
};

export function SettingsDrawer({ projectPath }: Props) {
  const [accountName, setAccountName] = useState("Local developer");
  const [accountEmail, setAccountEmail] = useState("");
  const [draft, setDraft] = useState<KeyDraft>({ provider: providers[0], label: "" });
  const [keys, setKeys] = useState<KeyDraft[]>([]);

  const workspaceName = useMemo(() => {
    const parts = projectPath.replace(/\\/g, "/").split("/").filter(Boolean);
    return parts[parts.length - 1] ?? projectPath;
  }, [projectPath]);

  return (
    <div className="space-y-5 p-3">
      <section>
        <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.18em] text-omnix-text-dim">
          account
        </div>
        <div className="space-y-2 rounded-lg border border-[var(--omnix-shell-border)] bg-[rgba(5,8,16,0.45)] p-3">
          <label className="block">
            <span className="mb-1 block font-mono text-[10px] text-omnix-text-dim">
              Display name
            </span>
            <input
              className="w-full rounded border border-[var(--omnix-shell-border)] bg-[rgba(5,8,16,0.7)] px-2 py-1.5 text-sm text-omnix-text-primary outline-none focus:border-omnix-accent-indigo/60"
              value={accountName}
              onChange={(e) => setAccountName(e.target.value)}
            />
          </label>
          <label className="block">
            <span className="mb-1 block font-mono text-[10px] text-omnix-text-dim">
              Email
            </span>
            <input
              className="w-full rounded border border-[var(--omnix-shell-border)] bg-[rgba(5,8,16,0.7)] px-2 py-1.5 text-sm text-omnix-text-primary outline-none focus:border-omnix-accent-indigo/60"
              value={accountEmail}
              onChange={(e) => setAccountEmail(e.target.value)}
              placeholder="you@example.com"
            />
          </label>
        </div>
      </section>

      <section>
        <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.18em] text-omnix-text-dim">
          vault
        </div>
        <div className="rounded-lg border border-[var(--omnix-shell-border)] bg-[rgba(5,8,16,0.45)] p-3">
          <div className="font-mono text-xs text-omnix-text-primary">{workspaceName}</div>
          <div className="mt-1 break-all font-mono text-[10px] text-omnix-text-dim">
            {projectPath}
          </div>
          <div className="mt-3 grid grid-cols-2 gap-2">
            <div className="rounded border border-[var(--omnix-shell-border)] p-2">
              <div className="font-mono text-[10px] text-omnix-text-dim">Storage</div>
              <div className="mt-1 text-xs text-omnix-text-primary">Local vault</div>
            </div>
            <div className="rounded border border-[var(--omnix-shell-border)] p-2">
              <div className="font-mono text-[10px] text-omnix-text-dim">Mode</div>
              <div className="mt-1 text-xs text-omnix-text-primary">Read-only UI</div>
            </div>
          </div>
        </div>
      </section>

      <section>
        <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.18em] text-omnix-text-dim">
          provider keys
        </div>
        <div className="space-y-2 rounded-lg border border-[var(--omnix-shell-border)] bg-[rgba(5,8,16,0.45)] p-3">
          <div className="grid grid-cols-[1fr_1.2fr] gap-2">
            <select
              className="rounded border border-[var(--omnix-shell-border)] bg-[#050810] px-2 py-1.5 text-sm text-omnix-text-primary outline-none"
              value={draft.provider}
              onChange={(e) => setDraft((prev) => ({ ...prev, provider: e.target.value }))}
            >
              {providers.map((provider) => (
                <option key={provider}>{provider}</option>
              ))}
            </select>
            <input
              className="rounded border border-[var(--omnix-shell-border)] bg-[rgba(5,8,16,0.7)] px-2 py-1.5 text-sm text-omnix-text-primary outline-none focus:border-omnix-accent-indigo/60"
              value={draft.label}
              onChange={(e) => setDraft((prev) => ({ ...prev, label: e.target.value }))}
              placeholder="Key label"
            />
          </div>
          <button
            type="button"
            className="w-full rounded border border-omnix-accent-indigo/35 px-2 py-1.5 text-xs text-omnix-text-primary hover:bg-[rgba(99,102,241,0.1)]"
            onClick={() => {
              if (!draft.label.trim()) return;
              setKeys((prev) => [...prev, { ...draft, label: draft.label.trim() }]);
              setDraft((prev) => ({ ...prev, label: "" }));
            }}
          >
            Add provider key placeholder
          </button>
          <div className="space-y-1">
            {keys.length === 0 ? (
              <div className="text-xs text-omnix-text-dim">
                Keys added here are UI placeholders until Provider Fabric wiring lands.
              </div>
            ) : (
              keys.map((key, index) => (
                <div
                  key={`${key.provider}:${key.label}:${index}`}
                  className="flex items-center justify-between rounded border border-[var(--omnix-shell-border)] px-2 py-1.5"
                >
                  <span className="font-mono text-xs text-omnix-text-primary">
                    {key.provider}
                  </span>
                  <span className="truncate font-mono text-[10px] text-omnix-text-dim">
                    {key.label}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
