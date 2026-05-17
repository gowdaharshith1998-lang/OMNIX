import { useEffect, useState } from "react";
import { chunkText } from "@/lib/streamingChunker";
import { useActionDispatchStore, type AgentActionTab } from "@/state/actionDispatchStore";
import { ResponseBlocks, ToolSteps } from "./ResponseBlocks";

export function AgentTabSurface({
  tab,
  tabId,
}: {
  tab?: AgentActionTab;
  tabId?: `agent:${string}`;
}) {
  const storeTab = useActionDispatchStore((s) =>
    tabId ? s.agentTabs.find((item) => item.id === tabId) : undefined
  );
  const activeTab = tab ?? storeTab;
  const retry = useActionDispatchStore((s) => s.retryAgentTab);
  const [visible, setVisible] = useState("");
  const errorMessage = activeTab?.result?.errorMessage || activeTab?.error || "Action failed.";
  const errorClass = activeTab?.result?.errorClass || activeTab?.result?.error;

  useEffect(() => {
    if (activeTab?.status !== "done" || !activeTab.result) {
      setVisible("");
      return;
    }
    const controller = new AbortController();
    void (async () => {
      for await (const chunk of chunkText(activeTab.result?.text ?? "", 20, 50, controller.signal)) {
        setVisible(chunk);
      }
    })();
    return () => controller.abort();
  }, [activeTab?.result, activeTab?.status]);

  if (!activeTab) return null;

  return (
    <div className="space-y-3 p-3">
      <div>
        <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-omnix-text-dim">
          action agent
        </div>
        <h3 className="mt-1 font-display text-base font-bold text-omnix-text-primary">
          {activeTab.descriptor.title}
        </h3>
      </div>

      {activeTab.status === "queued" && (
        <div className="rounded border border-amber-400/30 bg-amber-400/5 p-2 text-sm text-amber-100">
          queued
        </div>
      )}
      {activeTab.status === "loading" && (
        <div className="text-sm text-omnix-text-muted">Thinking...</div>
      )}
      {activeTab.status === "error" && (
        <div className="space-y-2 rounded border border-rose-400/30 bg-rose-400/5 p-2">
          <p className="text-sm text-rose-200">{errorMessage}</p>
          {errorClass && (
            <span className="inline-block rounded border border-rose-300/30 px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wide text-rose-100/80">
              {errorClass}
            </span>
          )}
          <button
            type="button"
            className="rounded border border-rose-300/40 px-2 py-1 font-mono text-[10px] uppercase text-rose-100"
            onClick={() => retry(activeTab.id)}
          >
            Retry
          </button>
        </div>
      )}
      {activeTab.status === "done" && activeTab.result && (
        <>
          <ToolSteps
            steps={activeTab.result.toolSteps}
            capped={activeTab.result.capped}
            capReason={activeTab.result.capReason}
          />
          {activeTab.result.costCapTriggered && (
            <div className="rounded border border-amber-300/30 bg-amber-300/5 p-2 text-xs text-amber-100">
              Tool output was capped to control cost.
            </div>
          )}
          <ResponseBlocks text={visible || activeTab.result.text} />
          <div className="font-mono text-[10px] text-omnix-text-dim">
            {activeTab.result.provider} · {activeTab.result.model} · in{" "}
            {activeTab.result.tokensIn} / out {activeTab.result.tokensOut} ·{" "}
            {activeTab.result.latencyMs}ms
          </div>
        </>
      )}
    </div>
  );
}
