import { Component, type ErrorInfo, type ReactNode } from "react";

type Props = {
  children: ReactNode;
  onRetry: () => void;
};

type State = {
  hasError: boolean;
  error?: Error;
};

export class ConstellationBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, _info: ErrorInfo) {
    void error;
    /* Errors surface via in-canvas fallback UI; avoid console noise in tests (R3). */
  }

  reset = () => {
    this.setState({ hasError: false, error: undefined });
    this.props.onRetry();
  };

  render() {
    if (this.state.hasError) {
      return (
        <div
          className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-4 bg-[rgba(2,6,21,0.92)] px-6 text-center font-mono text-sm text-omnix-text-primary backdrop-blur-md"
          data-omnix-constellation-fallback="1"
        >
          <p className="max-w-md text-omnix-text-muted">
            Constellation render failed
            {this.state.error?.message ? (
              <span className="mt-2 block text-[11px] text-omnix-text-dim">
                {this.state.error.message}
              </span>
            ) : null}
          </p>
          <div className="flex flex-wrap justify-center gap-2">
            <button
              type="button"
              className="rounded-md border border-omnix-accent-indigo/40 bg-[rgba(99,102,241,0.15)] px-3 py-1.5 text-xs uppercase tracking-wide text-omnix-text-primary transition hover:border-omnix-accent-indigo hover:bg-[rgba(99,102,241,0.25)]"
              onClick={this.reset}
            >
              Retry
            </button>
            <button
              type="button"
              title="Press F12 (Chromium) to open developer tools"
              className="rounded-md border border-omnix-accent-indigo/25 px-3 py-1.5 text-xs uppercase tracking-wide text-omnix-text-muted transition hover:border-omnix-accent-indigo/40 hover:text-omnix-text-primary"
            >
              Open devtools
            </button>
          </div>
          <p className="text-[10px] text-omnix-text-dim">
            Use browser devtools (F12) — Console / WebGPU tabs for engine detail.
          </p>
        </div>
      );
    }
    return this.props.children;
  }
}
