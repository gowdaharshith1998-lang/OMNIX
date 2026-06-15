import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT =
  true;

import {
  configureStudioScopeHandlers,
  resetStudioScopeForTests,
  setValidScopeIds,
  setScope,
  useScope,
} from "@/store/studioScopeStore";

function DualScopeReader() {
  const { currentScope } = useScope();
  const { currentScope: passive } = useScope({ subscribe: false });
  return (
    <>
      <span data-testid="a">{currentScope}</span>
      <span data-testid="ns">{passive}</span>
    </>
  );
}

function ConsumerA({ onRender }: { onRender: () => void }) {
  const { currentScope } = useScope();
  onRender();
  return <span data-testid="a">{currentScope}</span>;
}

function ConsumerB({ onRender }: { onRender: () => void }) {
  const { currentScope } = useScope();
  onRender();
  return <span data-testid="b">{currentScope}</span>;
}

function ConsumerC({ onRender }: { onRender: () => void }) {
  const { currentScope } = useScope();
  onRender();
  return <span data-testid="c">{currentScope}</span>;
}

afterEach(() => {
  document.body.textContent = "";
  resetStudioScopeForTests();
});

beforeEach(() => {
  resetStudioScopeForTests();
  setValidScopeIds(["repo", "crypto", "av2", "hyb"]);
});

describe("scope atom", () => {
  it("happy path: setScope('crypto') updates useScope on next render", () => {
    let root: Root | null = null;
    const container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => {
      root!.render(<ConsumerA onRender={() => undefined} />);
    });
    expect(container.querySelector('[data-testid="a"]')?.textContent).toBe("repo");
    act(() => {
      setScope("crypto");
    });
    expect(container.querySelector('[data-testid="a"]')?.textContent).toBe("crypto");
    act(() => root!.unmount());
  });

  it("atomicity: one setScope notifies all subscribers in the same React batch", () => {
    const renders = { a: 0, b: 0, c: 0 };
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    act(() => {
      root.render(
        <>
          <ConsumerA onRender={() => { renders.a += 1; }} />
          <ConsumerB onRender={() => { renders.b += 1; }} />
          <ConsumerC onRender={() => { renders.c += 1; }} />
        </>
      );
    });
    const afterMount = { ...renders };
    act(() => {
      setScope("av2");
    });
    expect(renders.a).toBe(afterMount.a + 1);
    expect(renders.b).toBe(afterMount.b + 1);
    expect(renders.c).toBe(afterMount.c + 1);
    act(() => root.unmount());
  });

  it("rejection: invalid scope does not mutate state and reports error", () => {
    const onInvalid = vi.fn();
    configureStudioScopeHandlers({ onInvalidScope: onInvalid });
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    act(() => {
      root.render(<ConsumerA onRender={() => undefined} />);
    });
    const before = container.querySelector('[data-testid="a"]')?.textContent ?? "";
    expect(before).toBe("repo");
    act(() => {
      root.unmount();
    });

    const ok = setScope("nonexistent_scope_id");
    expect(ok).toBe(false);
    expect(onInvalid).toHaveBeenCalledWith("nonexistent_scope_id");

    const container2 = document.createElement("div");
    document.body.appendChild(container2);
    const root2 = createRoot(container2);
    act(() => {
      root2.render(<ConsumerA onRender={() => undefined} />);
    });
    const after = container2.querySelector('[data-testid="a"]')?.textContent ?? "";
    expect(after).toBe("repo");
    act(() => {
      root2.unmount();
    });
  });

  it("concurrency: rapid successive setScope collapses to latest scope without torn reads", () => {
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    act(() => {
      root.render(<DualScopeReader />);
    });
    act(() => {
      setScope("crypto");
      setScope("av2");
      setScope("hyb");
    });
    expect(container.querySelector('[data-testid="a"]')?.textContent).toBe("hyb");
    expect(container.querySelector('[data-testid="ns"]')?.textContent).toBe("hyb");
    act(() => root.unmount());
  });
});
