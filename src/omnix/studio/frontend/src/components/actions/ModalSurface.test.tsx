import { describe, expect, it } from "vitest";
import { createRoot } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { ModalSurface } from "./ModalSurface";

describe("ModalSurface", () => {
  it("renders structured error message and class badge", () => {
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = createRoot(host);
    act(() => {
      root.render(
        <ModalSurface
          modal={{
            id: "modal-error",
            status: "error",
            error: "provider_error",
            descriptor: {
              id: "xray.diagnostics.god_file.split",
              title: "Split God File",
              kind: "decision",
              prompt: "split",
              workspaceId: "wid",
              source: { kind: "card", cardId: "xray" },
              applyLabel: "Apply",
              cancelLabel: "Cancel",
              onApply: () => undefined,
            },
            result: {
              ok: false,
              text: "",
              provider: "openai",
              model: "gpt-test",
              tokensIn: 0,
              tokensOut: 0,
              latencyMs: 12,
              error: "provider_error",
              errorClass: "provider_error",
              errorMessage: "OpenAI: Incorrect API key provided (401)",
              httpStatus: 401,
              retryable: false,
              toolSteps: [],
            },
          }}
        />
      );
    });
    expect(host.textContent).toContain("OpenAI: Incorrect API key provided (401)");
    expect(host.textContent).toContain("provider_error");
    expect(host.textContent).toContain("Retry");
    act(() => root.unmount());
    host.remove();
  });
});
