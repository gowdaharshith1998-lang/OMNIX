import type { LeftRailDrawer } from "@/components/LeftRail";

export const LEFT_DRAWER_MIN = 240;
export const LEFT_DRAWER_MAX = 480;
export const LEFT_DRAWER_DEFAULT = 300;
export const RIGHT_PANEL_MIN = 360;
export const RIGHT_PANEL_MAX = 640;
export const RIGHT_PANEL_DEFAULT = 440;

export type ShellLayoutState = {
  leftDrawer: {
    width: number;
    openTab: LeftRailDrawer | null;
  };
  rightPanel: {
    width: number;
    collapsed: boolean;
  };
};

export const defaultShellLayout: ShellLayoutState = {
  leftDrawer: { width: LEFT_DRAWER_DEFAULT, openTab: null },
  rightPanel: { width: RIGHT_PANEL_DEFAULT, collapsed: false },
};

function key(workspaceId: string) {
  return `omnix.shell.widths.${workspaceId}`;
}

export function clampWidth(value: number, min: number, max: number) {
  if (!Number.isFinite(value)) return min;
  return Math.max(min, Math.min(max, Math.round(value)));
}

export function loadShellLayout(workspaceId: string): ShellLayoutState {
  if (typeof localStorage === "undefined") return defaultShellLayout;
  try {
    const raw = localStorage.getItem(key(workspaceId));
    if (!raw) return defaultShellLayout;
    const parsed = JSON.parse(raw) as Partial<ShellLayoutState>;
    return normalizeShellLayout(parsed);
  } catch {
    return defaultShellLayout;
  }
}

export function saveShellLayout(workspaceId: string, state: ShellLayoutState) {
  if (typeof localStorage === "undefined") return;
  localStorage.setItem(key(workspaceId), JSON.stringify(normalizeShellLayout(state)));
}

export function normalizeShellLayout(
  state: Partial<ShellLayoutState>
): ShellLayoutState {
  return {
    leftDrawer: {
      width: clampWidth(
        state.leftDrawer?.width ?? LEFT_DRAWER_DEFAULT,
        LEFT_DRAWER_MIN,
        LEFT_DRAWER_MAX
      ),
      openTab: state.leftDrawer?.openTab ?? null,
    },
    rightPanel: {
      width: clampWidth(
        state.rightPanel?.width ?? RIGHT_PANEL_DEFAULT,
        RIGHT_PANEL_MIN,
        RIGHT_PANEL_MAX
      ),
      collapsed: Boolean(state.rightPanel?.collapsed),
    },
  };
}
