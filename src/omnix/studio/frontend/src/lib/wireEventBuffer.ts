import { useSyncExternalStore } from "react";
import type { WireEvent } from "@/components/inspector/AgentTab";

type Listener = () => void;

type Buffer = {
  events: WireEvent[];
  listeners: Set<Listener>;
};

const MAX_EVENTS = 200;
const byWorkspace = new Map<string, Buffer>();

function bufferFor(workspaceId: string): Buffer {
  const existing = byWorkspace.get(workspaceId);
  if (existing) return existing;
  const b: Buffer = { events: [], listeners: new Set() };
  byWorkspace.set(workspaceId, b);
  return b;
}

export function pushWireEvent(workspaceId: string, event: WireEvent): void {
  const b = bufferFor(workspaceId);
  b.events = [event, ...b.events];
  if (b.events.length > MAX_EVENTS) b.events = b.events.slice(0, MAX_EVENTS);
  if (b.listeners.size > 0) {
    for (const l of b.listeners) l();
  }
}

export function useWireEvents(workspaceId: string): WireEvent[] {
  const b = bufferFor(workspaceId);
  return useSyncExternalStore(
    (listener) => {
      b.listeners.add(listener);
      return () => b.listeners.delete(listener);
    },
    () => bufferFor(workspaceId).events,
    () => []
  );
}

export function __resetWireEventsForTests(workspaceId: string): void {
  const b = byWorkspace.get(workspaceId);
  if (!b) return;
  b.events = [];
  for (const l of b.listeners) l();
}

