/**
 * WebSocket client: subscribe, reconnect with backoff, application heartbeat (ping).
 */

const HEARTBEAT_MS = 25_000;
const MAX_BACKOFF_MS = 30_000;
const OPEN_TIMEOUT_MS = 12_000;

export type WsHandler = (msg: Record<string, unknown>) => void;
export type WsStateHandler = (state: "connecting" | "open" | "closed") => void;

function wsBaseUrl(): string {
  const p = location.protocol === "https:" ? "wss" : "ws";
  return `${p}://${location.host}`;
}

export class StudioWebSocket {
  private readonly workspaceId: string;
  private readonly onMessage: WsHandler;
  private readonly onState: WsStateHandler | undefined;
  private readonly onCloseCode: ((code: number) => void) | undefined;
  private socket: WebSocket | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private heartbeatTimer: ReturnType<typeof setTimeout> | null = null;
  private backoffMs = 1000;
  private closed = false;
  private readonly url: string;

  constructor(
    workspaceId: string,
    onMessage: WsHandler,
    onState?: WsStateHandler,
    onCloseCode?: (code: number) => void
  ) {
    this.workspaceId = workspaceId;
    this.onMessage = onMessage;
    this.onState = onState;
    this.onCloseCode = onCloseCode;
    this.url = `${wsBaseUrl()}/ws/workspace/${encodeURIComponent(workspaceId)}`;
  }

  connect(): void {
    this.closed = false;
    this._clearReconnect();
    this._open();
  }

  private _emit(s: "connecting" | "open" | "closed"): void {
    this.onState?.(s);
  }

  private _open(): void {
    if (this.closed) return;
    this._emit("connecting");
    const ws = new WebSocket(this.url);
    this.socket = ws;
    const failTimer = setTimeout(() => {
      if (ws.readyState !== WebSocket.OPEN) {
        try {
          ws.close();
        } catch {
          /* ignore */
        }
      }
    }, OPEN_TIMEOUT_MS);

    ws.onopen = () => {
      clearTimeout(failTimer);
      this.backoffMs = 1000;
      this._emit("open");
      const sub = JSON.stringify({
        type: "subscribe",
        workspace_id: this.workspaceId,
      });
      ws.send(sub);
      this._armHeartbeat();
    };

    ws.onmessage = (ev) => {
      try {
        const o = JSON.parse(String(ev.data)) as Record<string, unknown>;
        this.onMessage(o);
      } catch {
        /* ignore */
      }
    };

    ws.onerror = () => {
      /* onclose will reconnect */
    };

    ws.onclose = (ev) => {
      const code = ev instanceof CloseEvent ? ev.code : 0;
      clearTimeout(failTimer);
      this.onCloseCode?.(code);
      this._emit("closed");
      this._clearHeartbeat();
      this.socket = null;
      if (!this.closed) this._scheduleReconnect();
    };
  }

  private _scheduleReconnect(): void {
    this._clearReconnect();
    const d = this.backoffMs;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.backoffMs = Math.min(this.backoffMs * 2, MAX_BACKOFF_MS);
      this._open();
    }, d);
  }

  private _clearReconnect(): void {
    if (this.reconnectTimer != null) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  private _armHeartbeat(): void {
    this._clearHeartbeat();
    this.heartbeatTimer = setInterval(() => {
      if (this.socket?.readyState === WebSocket.OPEN) {
        this.socket.send(
          JSON.stringify({ type: "ping", ts: performance.now() / 1000 })
        );
      }
    }, HEARTBEAT_MS);
  }

  private _clearHeartbeat(): void {
    if (this.heartbeatTimer != null) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  close(): void {
    this.closed = true;
    this._clearReconnect();
    this._clearHeartbeat();
    try {
      this.socket?.close();
    } catch {
      /* ignore */
    }
    this.socket = null;
  }
}
