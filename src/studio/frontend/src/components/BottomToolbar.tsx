type Props = {
  onGraph?: () => void;
  onSearch?: () => void;
  onSave?: () => void;
};

export function BottomToolbar({ onGraph, onSearch, onSave }: Props) {
  const btn =
    "rounded border border-studio-line bg-studio-panel/80 px-2 py-1 text-[11px] text-slate-300 hover:border-studio-accent hover:text-white";
  return (
    <div className="flex items-center justify-between border-t border-studio-line bg-black/50 px-3 py-1.5 text-studio-muted">
      <div className="flex gap-1">
        <button type="button" className={btn} onClick={onGraph}>
          Graph
        </button>
        <button type="button" className={btn} onClick={onSearch}>
          Find
        </button>
        <button type="button" className={btn} onClick={onSave}>
          Save
        </button>
      </div>
      <div className="font-mono text-[10px]">
        <kbd className="rounded border border-studio-line px-1">⌘P</kbd> file ·{" "}
        <kbd className="rounded border border-studio-line px-1">⌘N</kbd> new ·{" "}
        <kbd className="rounded border border-studio-line px-1">⌘S</kbd> save
      </div>
    </div>
  );
}
