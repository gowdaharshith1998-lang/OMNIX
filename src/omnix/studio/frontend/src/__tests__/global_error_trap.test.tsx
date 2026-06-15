import { act, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT =
  true;

if (typeof PromiseRejectionEvent === "undefined") {
  globalThis.PromiseRejectionEvent = class extends Event {
    readonly promise: Promise<unknown>;
    readonly reason: unknown;
    constructor(
      type: string,
      init: { promise: Promise<unknown>; reason: unknown }
    ) {
      super(type);
      this.promise = init.promise;
      this.reason = init.reason;
    }
  } as typeof PromiseRejectionEvent;
}

import { installGlobalErrorTrap } from "@/lib/globalErrorTrap";

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

function TrapHarness(props: { onToast: (msg: string) => void }) {
  const [toast, setToast] = useState<string | null>(null);
  const onToastRef = useRef(props.onToast);
  onToastRef.current = props.onToast;
  useEffect(() => {
    const off = installGlobalErrorTrap({
      onToast: (m, d) => {
        onToastRef.current(m);
        setToast(m);
        void d;
      },
    });
    return off;
  }, []);
  return <div data-testid="trap-toast">{toast}</div>;
}

describe("global error trap", () => {
  it("window.onerror routes to toast with render error wording", async () => {
    const seen: string[] = [];
    const el = document.createElement("div");
    document.body.appendChild(el);
    const root = createRoot(el);

    await act(async () => {
      root.render(<TrapHarness onToast={(m) => seen.push(m)} />);
    });

    await act(async () => {
      const fn = window.onerror;
      expect(typeof fn).toBe("function");
      void (fn as OnErrorEventHandlerNonNull)(
        "synthetic onerror",
        "",
        0,
        0,
        new Error("synthetic onerror")
      );
    });

    await act(async () => {
      await vi.runAllTimersAsync();
    });

    expect(seen.some((s) => s.includes("synthetic onerror"))).toBe(true);

    root.unmount();
    document.body.removeChild(el);
  });

  it("debounces identical error storm into one toast with count suffix", async () => {
    const seen: string[] = [];
    const el = document.createElement("div");
    document.body.appendChild(el);
    const root = createRoot(el);

    await act(async () => {
      root.render(<TrapHarness onToast={(m) => seen.push(m)} />);
    });

    await act(async () => {
      const fn = window.onerror as OnErrorEventHandlerNonNull;
      for (let i = 0; i < 50; i++) {
        void fn("storm", "", 0, 0, new Error("storm"));
      }
    });

    await act(async () => {
      await vi.runAllTimersAsync();
    });

    expect(seen.length).toBe(1);
    expect(seen[0]).toContain("storm");
    expect(seen[0]).toMatch(/\(×50\)/);

    root.unmount();
    document.body.removeChild(el);
  });

  it("unhandledrejection routes to toast", async () => {
    const seen: string[] = [];
    const el = document.createElement("div");
    document.body.appendChild(el);
    const root = createRoot(el);

    await act(async () => {
      root.render(<TrapHarness onToast={(m) => seen.push(m)} />);
    });

    await act(async () => {
      const h = window.onunhandledrejection;
      expect(typeof h).toBe("function");
      const ev = new PromiseRejectionEvent("unhandledrejection", {
        promise: Promise.resolve(),
        reason: new Error("promise boom"),
      });
      (h as (e: PromiseRejectionEvent) => void)(ev);
    });

    await act(async () => {
      await vi.runAllTimersAsync();
    });

    expect(seen.some((s) => s.includes("promise boom"))).toBe(true);

    root.unmount();
    document.body.removeChild(el);
  });

  it("chains with an existing window.onerror handler", async () => {
    const chain: string[] = [];
    const prev = window.onerror;
    window.onerror = (message, source, lineno, colno, error) => {
      chain.push("legacy");
      if (typeof prev === "function") {
        return prev(message, source, lineno, colno, error) as boolean;
      }
      return false;
    };

    const el = document.createElement("div");
    document.body.appendChild(el);
    const root = createRoot(el);

    await act(async () => {
      root.render(<TrapHarness onToast={() => {}} />);
    });

    await act(async () => {
      const fn = window.onerror as OnErrorEventHandlerNonNull;
      void fn("chain-test", "", 0, 0, new Error("chain-test"));
    });

    await act(async () => {
      await vi.runAllTimersAsync();
    });

    expect(chain).toContain("legacy");

    root.unmount();
    document.body.removeChild(el);
    window.onerror = prev;
  });
});
