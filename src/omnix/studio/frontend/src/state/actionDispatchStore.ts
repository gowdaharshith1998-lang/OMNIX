import { create } from "zustand";
import { DispatchError, dispatchAction } from "@/lib/actions/dispatch";
import type {
  ActionDescriptor,
  ActionResult,
  AgentActionDescriptor,
  DecisionActionDescriptor,
} from "@/lib/actions/types";

export type ActionStatus = "queued" | "loading" | "done" | "error";

export type AgentActionTab = {
  id: `agent:${string}`;
  descriptor: AgentActionDescriptor;
  status: ActionStatus;
  result?: ActionResult;
  error?: string;
  controller?: AbortController;
};

export type DecisionActionModal = {
  id: string;
  descriptor: DecisionActionDescriptor;
  status: Exclude<ActionStatus, "queued">;
  result?: ActionResult;
  error?: string;
  controller?: AbortController;
  origin?: HTMLElement | null;
};

export type ActionDispatchState = {
  agentTabs: AgentActionTab[];
  activeModal: DecisionActionModal | null;
  modalQueue: DecisionActionModal[];
  openAgentTab: (descriptor: AgentActionDescriptor) => `agent:${string}`;
  closeAgentTab: (id: `agent:${string}`) => void;
  retryAgentTab: (id: `agent:${string}`) => void;
  openModal: (descriptor: DecisionActionDescriptor, origin?: HTMLElement | null) => void;
  closeModal: () => void;
  retryModal: () => void;
};

const MAX_IN_FLIGHT = 3;

function nextId(prefix: string) {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

function inFlightCount(tabs: AgentActionTab[]) {
  return tabs.filter((tab) => tab.status === "loading").length;
}

function startAgentDispatch(tab: AgentActionTab, set: StoreSet) {
  const controller = new AbortController();
  set((state: ActionDispatchState) => ({
    agentTabs: state.agentTabs.map((item) =>
      item.id === tab.id
        ? { ...item, status: "loading", error: undefined, result: undefined, controller }
        : item
    ),
  }));
  void dispatchAction(tab.descriptor, controller.signal)
    .then((result) => {
      set((state: ActionDispatchState) => ({
        agentTabs: state.agentTabs.map((item) =>
          item.id === tab.id ? { ...item, status: "done", result, controller: undefined } : item
        ),
      }));
      promoteQueued(set);
    })
    .catch((error) => {
      if (controller.signal.aborted) return;
      set((state: ActionDispatchState) => ({
        agentTabs: state.agentTabs.map((item) =>
          item.id === tab.id
            ? {
                ...item,
                status: "error",
                error: error instanceof Error ? error.message : String(error),
                result: error instanceof DispatchError ? error.result : item.result,
                controller: undefined,
              }
            : item
        ),
      }));
      promoteQueued(set);
    });
}

function promoteQueued(set: StoreSet) {
  set((state: ActionDispatchState) => {
    if (inFlightCount(state.agentTabs) >= MAX_IN_FLIGHT) return state;
    const queued = state.agentTabs.find((tab) => tab.status === "queued");
    if (!queued) return state;
    queueMicrotask(() => startAgentDispatch(queued, set));
    return state;
  });
}

function startModalDispatch(modal: DecisionActionModal, set: StoreSet) {
  const controller = new AbortController();
  set((state: ActionDispatchState) => ({
    activeModal:
          state.activeModal && state.activeModal.id === modal.id
        ? { ...state.activeModal, status: "loading", error: undefined, result: undefined, controller }
        : state.activeModal,
  }));
  void dispatchAction(modal.descriptor, controller.signal)
    .then((result) => {
      set((state: ActionDispatchState) => ({
        activeModal:
          state.activeModal && state.activeModal.id === modal.id
            ? { ...state.activeModal, status: "done", result, controller: undefined }
            : state.activeModal,
      }));
    })
    .catch((error) => {
      if (controller.signal.aborted) return;
      set((state: ActionDispatchState) => ({
        activeModal:
          state.activeModal && state.activeModal.id === modal.id
            ? {
                ...state.activeModal,
                status: "error",
                error: error instanceof Error ? error.message : String(error),
                result: error instanceof DispatchError ? error.result : state.activeModal?.result,
                controller: undefined,
              }
            : state.activeModal,
      }));
    });
}

type StoreSet = (
  partial:
    | ActionDispatchState
    | Partial<ActionDispatchState>
    | ((state: ActionDispatchState) => ActionDispatchState | Partial<ActionDispatchState>)
) => void;
type RouteActionResult = `agent:${string}` | void;

export const useActionDispatchStore = create<ActionDispatchState>((set, get) => ({
  agentTabs: [],
  activeModal: null,
  modalQueue: [],

  openAgentTab: (descriptor: AgentActionDescriptor) => {
    const id = `agent:${nextId(descriptor.id)}` as `agent:${string}`;
    const shouldQueue = inFlightCount(get().agentTabs) >= MAX_IN_FLIGHT;
    const tab: AgentActionTab = {
      id,
      descriptor,
      status: shouldQueue ? "queued" : "loading",
    };
    set((state: ActionDispatchState) => ({ agentTabs: [...state.agentTabs, tab] }));
    if (!shouldQueue) startAgentDispatch(tab, set);
    return id;
  },

  closeAgentTab: (id: `agent:${string}`) => {
    const tab = get().agentTabs.find((item: AgentActionTab) => item.id === id);
    tab?.controller?.abort();
    set((state: ActionDispatchState) => ({
      agentTabs: state.agentTabs.filter((item: AgentActionTab) => item.id !== id),
    }));
    promoteQueued(set);
  },

  retryAgentTab: (id: `agent:${string}`) => {
    const tab = get().agentTabs.find((item: AgentActionTab) => item.id === id);
    if (!tab) return;
    if (inFlightCount(get().agentTabs) >= MAX_IN_FLIGHT) {
      set((state: ActionDispatchState) => ({
        agentTabs: state.agentTabs.map((item) =>
          item.id === id ? { ...item, status: "queued", error: undefined } : item
        ),
      }));
      return;
    }
    startAgentDispatch(tab, set);
  },

  openModal: (descriptor: DecisionActionDescriptor, origin?: HTMLElement | null) => {
    const modal: DecisionActionModal = {
      id: nextId(descriptor.id),
      descriptor,
      status: "loading",
      origin,
    };
    if (get().activeModal) {
      set((state: ActionDispatchState) => ({ modalQueue: [...state.modalQueue, modal] }));
      return;
    }
    set({ activeModal: modal });
    startModalDispatch(modal, set);
  },

  closeModal: () => {
    const active = get().activeModal;
    active?.controller?.abort();
    active?.origin?.focus?.();
    const [next, ...rest] = get().modalQueue;
    set({ activeModal: next ?? null, modalQueue: rest });
    if (next) startModalDispatch(next, set);
  },

  retryModal: () => {
    const active = get().activeModal;
    if (!active) return;
    startModalDispatch(active, set);
  },
}));

export function routeAction(
  descriptor: ActionDescriptor,
  origin?: HTMLElement | null
): RouteActionResult {
  const store = useActionDispatchStore.getState();
  if (descriptor.kind === "agent") return store.openAgentTab(descriptor);
  return store.openModal(descriptor, origin);
}
