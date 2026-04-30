import { useMemo, useSyncExternalStore } from "react";

export type StudioScopeSnapshot = {
  currentScope: string;
  selectedNodeId: string | null;
};

type Listener = () => void;

let listeners = new Set<Listener>();

let snapshot: StudioScopeSnapshot = {
  currentScope: "repo",
  selectedNodeId: null,
};

/** Scope ids accepted by setScope — always includes repo. */
let validScopeIds = new Set<string>(["repo"]);

let invalidScopeReporter: (attemptedId: string) => void = () => {};

function emit() {
  listeners.forEach((l) => l());
}

function subscribe(listener: Listener) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function getServerSnapshot(): StudioScopeSnapshot {
  return snapshot;
}

export function configureStudioScopeHandlers(handlers: {
  onInvalidScope?: (id: string) => void;
}) {
  invalidScopeReporter =
    handlers.onInvalidScope ??
    (() => {
      /* noop */
    });
}

/** Replace valid scope ids (e.g. after graph bootstrap). Always ensures repo. */
export function setValidScopeIds(ids: Iterable<string>) {
  validScopeIds = new Set(ids);
  validScopeIds.add("repo");
}

export function getStudioScopeSnapshot(): StudioScopeSnapshot {
  return snapshot;
}

/**
 * Atomically updates current scope and clears selection.
 * @returns false when id is unknown (state unchanged, error reported).
 */
export function setScope(id: string): boolean {
  if (!validScopeIds.has(id)) {
    invalidScopeReporter(id);
    return false;
  }
  if (snapshot.currentScope === id && snapshot.selectedNodeId === null) {
    return true;
  }
  snapshot = { currentScope: id, selectedNodeId: null };
  emit();
  return true;
}

/**
 * Updates scope after imperative graph navigation. Keeps the current leaf selection
 * when its file path remains within the new scope prefix; clears on repo or mismatch.
 */
export function syncScopeFromViewer(
  id: string,
  opts: {
    pathPrefixForScope: (scopeId: string) => string | null;
    selectedFilePath: () => string | null;
  }
): void {
  if (!validScopeIds.has(id)) return;
  const prefix = opts.pathPrefixForScope(id);
  const fp = (opts.selectedFilePath() ?? "").replace(/\\/g, "/");
  let sel = snapshot.selectedNodeId;
  if (id === "repo") {
    sel = null;
  } else if (prefix && fp) {
    const pre = prefix.replace(/\\/g, "/");
    const under =
      fp === pre || fp.startsWith(pre + "/");
    if (!under) sel = null;
  } else if (prefix && !fp) {
    sel = null;
  }
  if (snapshot.currentScope === id && snapshot.selectedNodeId === sel) return;
  snapshot = { currentScope: id, selectedNodeId: sel };
  emit();
}

export function setSelectedNode(id: string | null) {
  if (snapshot.selectedNodeId === id) return;
  snapshot = { ...snapshot, selectedNodeId: id };
  emit();
}

export type UseScopeOptions = { subscribe?: boolean };

export function useScope(
  opts?: UseScopeOptions
): StudioScopeSnapshot & {
  setScope: typeof setScope;
  setSelectedNode: typeof setSelectedNode;
  syncScopeFromViewer: typeof syncScopeFromViewer;
} {
  const sub = opts?.subscribe !== false;
  const snap = sub
    ? useSyncExternalStore(subscribe, getServerSnapshot, getServerSnapshot)
    : getServerSnapshot();

  const actions = useMemo(
    () => ({
      setScope,
      setSelectedNode,
      syncScopeFromViewer,
    }),
    []
  );

  return { ...snap, ...actions };
}

/** Test helper — resets module state between vitest cases. */
export function resetStudioScopeForTests() {
  listeners = new Set();
  snapshot = { currentScope: "repo", selectedNodeId: null };
  validScopeIds = new Set(["repo"]);
  invalidScopeReporter = () => {};
}
