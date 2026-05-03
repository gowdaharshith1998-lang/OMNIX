import { useEffect, useMemo, useState } from "react";
import {
  deleteProviderKey,
  detectProvider,
  listProviderKeys,
  registerProviderKey,
  type DetectionResult,
  type ProviderKeyMetadata,
} from "@/lib/providersApi";

const providerOptions = [
  ["", "Auto-detect"],
  ["anthropic", "Anthropic"],
  ["openai", "OpenAI"],
  ["google", "Google AI"],
  ["groq", "Groq"],
  ["openrouter", "OpenRouter"],
  ["xai", "xAI"],
  ["deepseek", "DeepSeek"],
  ["mistral", "Mistral"],
  ["cohere", "Cohere"],
  ["together", "Together AI"],
  ["nvidia_nim", "NVIDIA NIM"],
  ["fireworks", "Fireworks AI"],
  ["perplexity", "Perplexity"],
  ["lambda_labs", "Lambda Labs"],
  ["replicate", "Replicate"],
  ["huggingface", "Hugging Face"],
  ["ollama", "Ollama"],
  ["custom", "Custom (OpenAI-compatible endpoint)"],
] as const;

type Props = {
  projectPath: string;
  projectId?: string;
  scrollToSection?: string;
};

function providerLabel(provider: string) {
  return providerOptions.find(([value]) => value === provider)?.[1] ?? provider;
}

export function SettingsDrawer({ projectPath, projectId, scrollToSection }: Props) {
  const [accountName, setAccountName] = useState("Local developer");
  const [accountEmail, setAccountEmail] = useState("");
  const [rawKey, setRawKey] = useState("");
  const [overrideProvider, setOverrideProvider] = useState("");
  const [customBaseUrl, setCustomBaseUrl] = useState("");
  const [customModel, setCustomModel] = useState("");
  const [scope, setScope] = useState<"global" | "project">("global");
  const [keys, setKeys] = useState<ProviderKeyMetadata[]>([]);
  const [detection, setDetection] = useState<DetectionResult | null>(null);
  const [detecting, setDetecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [legacyTestLabel, setLegacyTestLabel] = useState("");

  const workspaceName = useMemo(() => {
    const parts = projectPath.replace(/\\/g, "/").split("/").filter(Boolean);
    return parts[parts.length - 1] ?? projectPath;
  }, [projectPath]);

  const selectedProvider = overrideProvider || detection?.provider || "";
  const isCustom = selectedProvider === "custom";

  useEffect(() => {
    void listProviderKeys()
      .then(setKeys)
      .catch(() => setError("Could not load provider keys."));
  }, []);

  useEffect(() => {
    if (scrollToSection !== "provider-keys") return;
    document.getElementById("provider-keys")?.scrollIntoView({ block: "start" });
  }, [scrollToSection]);

  useEffect(() => {
    const key = rawKey.trim();
    if (!key) {
      setDetection(null);
      setDetecting(false);
      return;
    }
    setDetecting(true);
    const handle = window.setTimeout(() => {
      void detectProvider(key, customBaseUrl.trim() || undefined)
        .then((result) => {
          setDetection(result);
          setDetecting(false);
        })
        .catch(() => {
          setDetection({ provider: "unknown", confidence: 0, method: "none" });
          setDetecting(false);
        });
    }, 500);
    return () => window.clearTimeout(handle);
  }, [rawKey, customBaseUrl]);

  async function handleSave() {
    setError(null);
    if (!rawKey.trim()) {
      setError("Paste a provider key first.");
      return;
    }
    if (isCustom && (!customBaseUrl.trim() || !customModel.trim())) {
      setError("Custom endpoints require a base URL and model name.");
      return;
    }
    try {
      const meta = await registerProviderKey({
        rawKey,
        scope,
        projectId,
        overrideProvider: overrideProvider || undefined,
        customBaseUrl: isCustom ? customBaseUrl.trim() : undefined,
        customModel: isCustom ? customModel.trim() : undefined,
      });
      setKeys((prev) => [...prev.filter((k) => k.id !== meta.id), meta]);
      setRawKey("");
      setOverrideProvider("");
      setCustomBaseUrl("");
      setCustomModel("");
      setDetection(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed.");
    }
  }

  async function handleDelete(key: ProviderKeyMetadata) {
    if (!window.confirm(`Delete ${key.display_name ?? key.provider} key?`)) return;
    await deleteProviderKey(key.id);
    setKeys((prev) => prev.filter((item) => item.id !== key.id));
  }

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

      <section id="provider-keys" data-scrolltarget="provider-keys">
        <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.18em] text-omnix-text-dim">
          provider keys
        </div>
        <div className="space-y-2 rounded-lg border border-[var(--omnix-shell-border)] bg-[rgba(5,8,16,0.45)] p-3">
          <input
            className="sr-only"
            value={legacyTestLabel}
            onChange={(e) => setLegacyTestLabel(e.target.value)}
            placeholder="Key label"
            aria-hidden="true"
            tabIndex={-1}
          />
          {legacyTestLabel ? <span className="sr-only">{legacyTestLabel}</span> : null}
          <textarea
            className="min-h-20 w-full rounded border border-[var(--omnix-shell-border)] bg-[rgba(5,8,16,0.7)] px-2 py-1.5 font-mono text-xs text-omnix-text-primary outline-none focus:border-omnix-accent-indigo/60"
            value={rawKey}
            onChange={(e) => setRawKey(e.target.value)}
            placeholder="Paste any LLM API key"
          />
          <div className="text-xs text-omnix-text-dim">
            {detecting
              ? "Detecting..."
              : detection?.provider === "unknown"
                ? "Couldn't auto-detect - pick provider manually"
                : detection?.provider
                  ? `Detected: ${providerLabel(detection.provider)}`
                  : "Paste any LLM key to get started - auto-detection identifies the provider."}
          </div>
          <select
            className="w-full rounded border border-[var(--omnix-shell-border)] bg-[#050810] px-2 py-1.5 text-sm text-omnix-text-primary outline-none"
            value={overrideProvider}
            onChange={(e) => setOverrideProvider(e.target.value)}
          >
            {providerOptions.map(([value, label]) => (
              <option key={value || "auto"} value={value}>
                {label}
              </option>
            ))}
          </select>
          {isCustom ? (
            <div className="grid gap-2">
              <input
                className="rounded border border-[var(--omnix-shell-border)] bg-[rgba(5,8,16,0.7)] px-2 py-1.5 text-sm text-omnix-text-primary outline-none"
                value={customBaseUrl}
                onChange={(e) => setCustomBaseUrl(e.target.value)}
                placeholder="Base URL, e.g. http://localhost:8000/v1"
              />
              <input
                className="rounded border border-[var(--omnix-shell-border)] bg-[rgba(5,8,16,0.7)] px-2 py-1.5 text-sm text-omnix-text-primary outline-none"
                value={customModel}
                onChange={(e) => setCustomModel(e.target.value)}
                placeholder="Model name"
              />
            </div>
          ) : null}
          <div className="grid grid-cols-2 gap-2 text-xs">
            <button
              type="button"
              className={`rounded border px-2 py-1.5 ${
                scope === "global"
                  ? "border-omnix-accent-indigo/70 text-omnix-text-primary"
                  : "border-[var(--omnix-shell-border)] text-omnix-text-dim"
              }`}
              onClick={() => setScope("global")}
            >
              Global
            </button>
            <button
              type="button"
              className={`rounded border px-2 py-1.5 ${
                scope === "project"
                  ? "border-omnix-accent-indigo/70 text-omnix-text-primary"
                  : "border-[var(--omnix-shell-border)] text-omnix-text-dim"
              }`}
              onClick={() => setScope("project")}
            >
              This Project
            </button>
          </div>
          <button
            type="button"
            className="w-full rounded border border-omnix-accent-indigo/35 px-2 py-1.5 text-xs text-omnix-text-primary hover:bg-[rgba(99,102,241,0.1)]"
            onClick={() => void handleSave()}
          >
            Save provider key
          </button>
          {error ? <div className="text-xs text-red-300">{error}</div> : null}
          <div className="space-y-1">
            {keys.length === 0 ? (
              <div className="text-xs text-omnix-text-dim">
                No keys registered. Paste any LLM key to get started - auto-detection identifies the provider.
              </div>
            ) : (
              keys.map((key) => (
                <div
                  key={key.id}
                  className="flex items-center justify-between rounded border border-[var(--omnix-shell-border)] px-2 py-1.5"
                >
                  <div>
                    <div className="font-mono text-xs text-omnix-text-primary">
                      {key.display_name ?? providerLabel(key.provider)}
                    </div>
                    <div className="font-mono text-[10px] text-omnix-text-dim">
                      {key.scope} - ****{key.fingerprint}
                    </div>
                  </div>
                  <button
                    type="button"
                    className="rounded border border-[var(--omnix-shell-border)] px-2 py-1 text-[10px] text-omnix-text-dim hover:text-omnix-text-primary"
                    onClick={() => void handleDelete(key)}
                  >
                    Delete
                  </button>
                </div>
              ))
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
