type Stats = {
  files: number;
  functions: number;
  classes: number;
  edges: number;
  dark_matter?: number;
  entangled?: number;
};

type Props = { stats: Stats; wsState: "connecting" | "open" | "closed" | "idle" };

function Dot({ ok }: { ok: boolean }) {
  return (
    <span
      className={
        "ml-1 inline-block h-2 w-2 rounded-full " +
        (ok ? "bg-emerald-500" : "bg-amber-500")
      }
    />
  );
}

export function StatsPanel({ stats, wsState }: Props) {
  const live = wsState === "open";
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-lg border border-studio-line bg-studio-panel/90 px-3 py-2 text-xs text-slate-200 shadow-lg backdrop-blur">
      <span className="font-mono text-studio-muted">graph</span>
      <span>
        files <b className="text-white">{stats.files}</b>
      </span>
      <span>
        fn <b className="text-white">{stats.functions}</b>
      </span>
      <span>
        cls <b className="text-white">{stats.classes}</b>
      </span>
      <span>
        edges <b className="text-white">{stats.edges}</b>
      </span>
      {(stats.dark_matter != null || stats.entangled != null) && (
        <>
          {stats.dark_matter != null && (
            <span>
              DM <b className="text-white">{stats.dark_matter}</b>
            </span>
          )}
          {stats.entangled != null && (
            <span>
              ent <b className="text-white">{stats.entangled}</b>
            </span>
          )}
        </>
      )}
      <span className="border-l border-studio-line pl-3 text-studio-muted">
        ws
        <span title={wsState}>
          <Dot ok={live} />
        </span>
        <span className="ml-1 font-mono text-[10px] uppercase">{wsState}</span>
      </span>
    </div>
  );
}
