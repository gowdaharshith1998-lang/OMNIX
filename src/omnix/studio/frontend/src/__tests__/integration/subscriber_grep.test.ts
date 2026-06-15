import { describe, expect, it } from "vitest";

const rawSources = import.meta.glob<string>(
  [
    "../../components/XRayTab.tsx",
    "../../components/StatsPanel.tsx",
    "../../components/Workspace.tsx",
    "../../components/Graph/GraphCanvas.tsx",
  ],
  { query: "?raw", import: "default", eager: true }
);

const consumersThatMustSubscribe = [
  "../../components/XRayTab.tsx",
  "../../components/StatsPanel.tsx",
  "../../components/Graph/GraphCanvas.tsx",
  "../../components/Workspace.tsx",
] as const;

describe("subscriber wiring (static)", () => {
  it.each(consumersThatMustSubscribe)("%s must subscribe to studioScopeStore", (rel) => {
    const src = rawSources[rel];
    expect(src).toBeTruthy();
    expect(src).toMatch(/from ['"][^'"]*studioScopeStore['"]/);
    expect(src).toMatch(/useScope|useStudioScope|useSyncExternalStore\(/);
  });
});
