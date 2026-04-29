import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { BugsDrawer } from "../BugsDrawer";
import { BugsScanConflictError, type BugsScanEvent } from "@/lib/api";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const apiMock = vi.hoisted(() => ({
  startBugsScan: vi.fn(),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    startBugsScan: apiMock.startBugsScan,
  };
});

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

beforeEach(() => {
  apiMock.startBugsScan.mockResolvedValue({ scan_id: "scan-1" });
});

afterEach(() => {
  document.body.textContent = "";
  vi.clearAllMocks();
});

describe("BugsDrawer", () => {
  it("starts a workspace bug scan from the SCAN button", async () => {
    const { container } = render(<BugsDrawer workspaceId="ws1" />);
    const scan = container.querySelector("button") as HTMLButtonElement;

    act(() => {
      scan.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    expect(apiMock.startBugsScan).toHaveBeenCalledWith("ws1");
    expect(container.textContent).toContain("Scanning...");
    await flush();
    expect(container.textContent).toContain("scan scan-1");
  });

  it("renders completed findings with severity badges", () => {
    const event: BugsScanEvent = {
      type: "bugs_scan_complete",
      scan_id: "scan-2",
      findings: [
        {
          file: "buggy.py",
          function: "unsafe_div",
          lineno: 1,
          severity_score: 12,
          failures: [
            {
              exception_type: "ZeroDivisionError",
              message: "division by zero",
              shrunk_input: "(0,)",
            },
          ],
        },
      ],
      summary: { findings_count: 1, files_scanned: 1, total_examples_run: 50 },
      wall_time_seconds: 0.2,
    };

    const { container } = render(<BugsDrawer workspaceId="ws1" scanEvent={event} />);

    expect(container.textContent).toContain("unsafe_div");
    expect(container.textContent).toContain("HIGH");
    expect(container.textContent).toContain("ZeroDivisionError: division by zero");
    expect(container.querySelector("[title='severity score: 12']")).not.toBeNull();
  });

  it("updates elapsed time from heartbeat events", () => {
    const event: BugsScanEvent = {
      type: "bugs_scan_heartbeat",
      scan_id: "scan-3",
      elapsed_seconds: 65,
    };

    const { container } = render(<BugsDrawer workspaceId="ws1" scanEvent={event} />);

    expect(container.textContent).toContain("Scanning...");
    expect(container.textContent).toContain("1m 5s");
  });

  it("sorts findings by file path", () => {
    const event: BugsScanEvent = {
      type: "bugs_scan_complete",
      scan_id: "scan-4",
      findings: [
        { file: "z.py", function: "zeta", severity_score: 20, failures: [] },
        { file: "a.py", function: "alpha", severity_score: 1, failures: [] },
      ],
      summary: { findings_count: 2, files_scanned: 2, total_examples_run: 100 },
      wall_time_seconds: 0.2,
    };
    const { container } = render(<BugsDrawer workspaceId="ws1" scanEvent={event} />);
    const fileButton = Array.from(container.querySelectorAll("button")).find(
      (button) => button.textContent === "file"
    );

    act(() => {
      fileButton?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    const text = container.textContent ?? "";
    expect(text.indexOf("alpha")).toBeLessThan(text.indexOf("zeta"));
  });

  it("toasts concurrent scan rejections", async () => {
    const onToast = vi.fn();
    apiMock.startBugsScan.mockRejectedValue(new BugsScanConflictError("scan-active"));
    const { container } = render(<BugsDrawer workspaceId="ws1" onToast={onToast} />);

    act(() => {
      container.querySelector("button")?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await flush();

    expect(onToast).toHaveBeenCalledWith(
      "Scan already running, wait for current to complete.",
      3500
    );
  });
});
