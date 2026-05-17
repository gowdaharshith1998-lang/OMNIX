import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { Simulate } from "react-dom/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const apiMock = vi.hoisted(() => ({
  getFile: vi.fn(),
  putFile: vi.fn(),
  listReceipts: vi.fn(),
  getFileTree: vi.fn(),
  searchWorkspace: vi.fn(),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    getFile: apiMock.getFile,
    putFile: apiMock.putFile,
    listReceipts: apiMock.listReceipts,
    getFileTree: apiMock.getFileTree,
    searchWorkspace: apiMock.searchWorkspace,
  };
});

vi.mock("@monaco-editor/react", () => ({
  default: function MockEditor(props: {
    value?: string;
    onChange?: (value: string) => void;
    onMount?: (editor: {
      getValue: () => string;
      setValue: (value: string) => void;
      revealLineInCenter: (line: number) => void;
      setPosition: (pos: { lineNumber: number; column: number }) => void;
    }) => void;
  }) {
    const valueRef = React.useRef(props.value ?? "");
    React.useEffect(() => {
      props.onMount?.({
        getValue: () => valueRef.current,
        setValue: (value: string) => {
          valueRef.current = value;
        },
        revealLineInCenter: vi.fn(),
        setPosition: vi.fn(),
      });
    }, []);
    return React.createElement("textarea", {
      "aria-label": "mock monaco",
      value: props.value ?? "",
      onChange: (e: React.ChangeEvent<HTMLTextAreaElement>) => {
        valueRef.current = e.target.value;
        props.onChange?.(e.target.value);
      },
    });
  },
}));

import { CodeTab, type CodeTabHandle } from "../CodeTab";
import { HistoryTab } from "../HistoryTab";
import { LeftRail, type LeftRailDrawer } from "../LeftRail";
import { RightPanel } from "../RightPanel";
import { BugsDrawer } from "../drawers/BugsDrawer";
import { FilesDrawer } from "../drawers/FilesDrawer";
import { ReceiptsDrawer } from "../drawers/ReceiptsDrawer";
import { SearchDrawer } from "../drawers/SearchDrawer";
import { SettingsDrawer } from "../drawers/SettingsDrawer";

function render(node: React.ReactElement): { root: Root; container: HTMLDivElement } {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => root.render(node));
  return { root, container };
}

async function flush() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

async function flushReceiptDebounce() {
  await act(async () => {
    vi.advanceTimersByTime(150);
    await Promise.resolve();
    await Promise.resolve();
  });
}

afterEach(() => {
  document.body.textContent = "";
  vi.useRealTimers();
  vi.clearAllMocks();
});

beforeEach(() => {
  apiMock.getFile.mockResolvedValue({
    path: "src/app.ts",
    content: "one\ntwo\nthree\n",
    last_modified: 1,
    language: "typescript",
  });
  apiMock.putFile.mockResolvedValue({ written: true, new_last_modified: 2 });
  apiMock.listReceipts.mockResolvedValue([
    {
      kind: "fabric.call",
      target: "openai",
      hash_prefix: "abcdef123456",
      sig_alg: "ML-DSA-65",
      mtime_iso: "2026-04-29T01:00:00Z",
      source: "fabric",
      path: "/tmp/r.json",
    },
  ]);
  apiMock.getFileTree.mockResolvedValue({
    name: "omnix",
    type: "dir",
    children: [
      { name: "README.md", type: "file", size: 100 },
      {
        name: "src",
        type: "dir",
        children: [{ name: "app.ts", type: "file", size: 200 }],
      },
    ],
  });
  apiMock.searchWorkspace.mockResolvedValue([
    { kind: "symbol", name: "run", path: "src/app.ts", line: 2, snippet: "" },
  ]);
});

describe("RightPanel", () => {
  it("mounts persistent tabs", () => {
    const { container } = render(
      <RightPanel
        tabs={[
          { id: "code", label: "Code", content: <div>code body</div> },
          { id: "history", label: "History", content: <div>history body</div> },
        ]}
        activeTab="code"
        width={440}
        onSelectTab={vi.fn()}
        onResizeEnd={vi.fn()}
      />
    );
    expect(container.textContent).toContain("Code");
    expect(container.textContent).toContain("code body");
  });

  it("interacts by selecting tabs", () => {
    const onSelect = vi.fn();
    const { container } = render(
      <RightPanel
        tabs={[
          { id: "code", label: "Code", content: <div>code body</div> },
          { id: "history", label: "History", content: <div>history body</div> },
        ]}
        activeTab="code"
        width={440}
        onSelectTab={onSelect}
        onResizeEnd={vi.fn()}
      />
    );
    const historyTab = Array.from(container.querySelectorAll("button")).find(
      (button) => button.textContent === "History"
    );
    act(() => historyTab?.dispatchEvent(new MouseEvent("click", { bubbles: true })));
    expect(onSelect).toHaveBeenCalledWith("history");
  });

  it("tears down cleanly", () => {
    const { root, container } = render(
      <RightPanel tabs={[{ id: "code", label: "Code", content: <div /> }]} activeTab="code" width={440} onSelectTab={vi.fn()} onResizeEnd={vi.fn()} />
    );
    act(() => root.unmount());
    expect(container.textContent).toBe("");
  });
});

describe("LeftRail", () => {
  it("mounts six surfaces", () => {
    const { container } = render(<LeftRail active={null} drawerWidth={300} onSelect={vi.fn()} onClose={vi.fn()} onResizeEnd={vi.fn()} />);
    expect(container.querySelectorAll(".omnix-rail-btn")).toHaveLength(6);
  });

  it("interacts by opening a drawer", () => {
    const onSelect = vi.fn();
    const { container } = render(<LeftRail active={null} drawerWidth={300} onSelect={onSelect} onClose={vi.fn()} onResizeEnd={vi.fn()} />);
    act(() => container.querySelector('[aria-label="Files"]')?.dispatchEvent(new MouseEvent("click", { bubbles: true })));
    expect(onSelect).toHaveBeenCalledWith("files");
  });

  it("tears down cleanly", () => {
    const { root, container } = render(<LeftRail active={"files" as LeftRailDrawer} drawerWidth={300} onSelect={vi.fn()} onClose={vi.fn()} onResizeEnd={vi.fn()} />);
    act(() => root.unmount());
    expect(container.textContent).toBe("");
  });
});

describe("CodeTab", () => {
  it("mounts empty state", () => {
    const { container } = render(<CodeTab workspaceId="w" target={null} externalFileEpoch={0} onToast={vi.fn()} />);
    expect(container.textContent).toContain("Select an entity in the brain");
  });

  it("interacts by saving edited Monaco content", async () => {
    const ref = React.createRef<CodeTabHandle>();
    render(<CodeTab ref={ref} workspaceId="w" target={{ path: "src/app.ts", lineStart: 2 }} externalFileEpoch={0} onToast={vi.fn()} />);
    await flush();
    const textarea = document.querySelector("textarea") as HTMLTextAreaElement;
    act(() => {
      Simulate.change(
        textarea,
        { target: { value: "changed" } } as unknown as Parameters<typeof Simulate.change>[1]
      );
    });
    act(() => ref.current?.save());
    await flush();
    expect(apiMock.putFile).toHaveBeenCalled();
  });

  it("tears down cleanly", () => {
    const { root, container } = render(<CodeTab workspaceId="w" target={null} externalFileEpoch={0} onToast={vi.fn()} />);
    act(() => root.unmount());
    expect(container.textContent).toBe("");
  });
});

describe("HistoryTab", () => {
  it("mounts receipt history", async () => {
    const { container } = render(<HistoryTab workspaceId="w" />);
    await flush();
    expect(container.textContent).toContain("fabric.call");
  });

  it("interacts with receipt fetch on mount", async () => {
    render(<HistoryTab workspaceId="w" />);
    await flush();
    expect(apiMock.listReceipts).toHaveBeenCalledWith("w", { limit: 100 });
  });

  it("tears down cleanly", () => {
    const { root, container } = render(<HistoryTab workspaceId="w" />);
    act(() => root.unmount());
    expect(container.textContent).toBe("");
  });
});

describe("drawers", () => {
  it("FilesDrawer mounts, interacts, and tears down", async () => {
    const onOpen = vi.fn();
    const { root, container } = render(<FilesDrawer workspaceId="w" onOpenFile={onOpen} />);
    await flush();
    act(() => container.querySelector("button")?.dispatchEvent(new MouseEvent("click", { bubbles: true })));
    expect(onOpen).toHaveBeenCalledWith("README.md");
    act(() => root.unmount());
    expect(container.textContent).toBe("");
  });

  it("FilesDrawer renders nested directories", async () => {
    const { container } = render(<FilesDrawer workspaceId="w" onOpenFile={vi.fn()} />);
    await flush();
    expect(container.textContent).toContain("src");
    expect(container.textContent).toContain("app.ts");
  });

  it("FilesDrawer handles empty trees", async () => {
    apiMock.getFileTree.mockResolvedValueOnce({ name: "empty", type: "dir", children: [] });
    const { container } = render(<FilesDrawer workspaceId="w" onOpenFile={vi.fn()} />);
    await flush();
    expect(container.textContent).toContain("graph-aware tree");
  });

  it("ReceiptsDrawer mounts, interacts, and tears down", async () => {
    vi.useFakeTimers();
    const { root, container } = render(<ReceiptsDrawer workspaceId="w" />);
    await flushReceiptDebounce();
    expect(container.textContent).toContain("audit log");
    act(() => container.querySelector("button")?.dispatchEvent(new MouseEvent("click", { bubbles: true })));
    act(() => root.unmount());
    expect(container.textContent).toBe("");
  });

  it("ReceiptsDrawer groups by source", async () => {
    vi.useFakeTimers();
    const { container } = render(<ReceiptsDrawer workspaceId="w" />);
    await flushReceiptDebounce();
    expect(container.textContent).toContain("fabric");
  });

  it("ReceiptsDrawer handles empty receipts", async () => {
    vi.useFakeTimers();
    apiMock.listReceipts.mockResolvedValueOnce([]);
    const { container } = render(<ReceiptsDrawer workspaceId="w" />);
    await flushReceiptDebounce();
    expect(container.textContent).toContain("No receipts found");
  });

  it("SearchDrawer mounts, interacts, and tears down", async () => {
    vi.useFakeTimers();
    const onQuery = vi.fn();
    const onOpen = vi.fn();
    const { root, container } = render(
      <SearchDrawer workspaceId="w" query="run" onQueryChange={onQuery} onOpenResult={onOpen} />
    );
    await act(async () => {
      vi.runAllTimers();
      await Promise.resolve();
    });
    act(() => container.querySelectorAll("button")[3]?.dispatchEvent(new MouseEvent("click", { bubbles: true })));
    expect(onOpen).toHaveBeenCalled();
    act(() => root.unmount());
    expect(container.textContent).toBe("");
  });

  it("SearchDrawer sends query changes upward", () => {
    const onQuery = vi.fn();
    const { container } = render(
      <SearchDrawer workspaceId="w" query="" onQueryChange={onQuery} onOpenResult={vi.fn()} />
    );
    const input = container.querySelector("input") as HTMLInputElement;
    act(() => {
      Simulate.change(
        input,
        { target: { value: "handler" } } as unknown as Parameters<typeof Simulate.change>[1]
      );
    });
    expect(onQuery).toHaveBeenCalledWith("handler");
  });

  it("SearchDrawer can filter by file kind", async () => {
    vi.useFakeTimers();
    render(<SearchDrawer workspaceId="w" query="app" onQueryChange={vi.fn()} onOpenResult={vi.fn()} />);
    const fileButton = Array.from(document.querySelectorAll("button")).find(
      (button) => button.textContent === "file"
    );
    act(() => fileButton?.dispatchEvent(new MouseEvent("click", { bubbles: true })));
    await act(async () => {
      vi.runAllTimers();
      await Promise.resolve();
    });
    expect(apiMock.searchWorkspace).toHaveBeenCalledWith("w", "app", "file", 50);
  });

  it("SettingsDrawer mounts, interacts, and tears down", () => {
    const { root, container } = render(<SettingsDrawer projectPath="/tmp/omnix" />);
    const input = container.querySelector('input[placeholder="Key label"]') as HTMLInputElement;
    act(() => {
      Simulate.change(
        input,
        { target: { value: "dev" } } as unknown as Parameters<typeof Simulate.change>[1]
      );
    });
    act(() => container.querySelector("button")?.dispatchEvent(new MouseEvent("click", { bubbles: true })));
    expect(container.textContent).toContain("dev");
    act(() => root.unmount());
    expect(container.textContent).toBe("");
  });

  it("SettingsDrawer updates account fields", () => {
    const { container } = render(<SettingsDrawer projectPath="/tmp/omnix" />);
    const input = container.querySelector("input") as HTMLInputElement;
    act(() => {
      Simulate.change(
        input,
        { target: { value: "Harsh" } } as unknown as Parameters<typeof Simulate.change>[1]
      );
    });
    expect(input.value).toBe("Harsh");
  });

  it("SettingsDrawer shows workspace vault path", () => {
    const { container } = render(<SettingsDrawer projectPath="/tmp/omnix" />);
    expect(container.textContent).toContain("/tmp/omnix");
  });

  it("BugsDrawer mounts with scan controls and tears down", () => {
    const { root, container } = render(<BugsDrawer workspaceId="w" />);
    expect(container.textContent).toContain("PBT bug scan");
    expect(container.querySelector("button")?.textContent).toContain("SCAN");
    act(() => root.unmount());
    expect(container.textContent).toBe("");
  });

  it("BugsDrawer exposes an idle scan button", () => {
    const { container } = render(<BugsDrawer workspaceId="w" />);
    expect(container.querySelector("button")?.textContent).toContain("SCAN");
  });

  it("BugsDrawer shows the empty findings state", () => {
    const { container } = render(<BugsDrawer workspaceId="w" />);
    expect(container.textContent).toContain("No findings yet");
  });
});
