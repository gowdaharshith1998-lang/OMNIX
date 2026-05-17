type Props = {
  value: string;
  onChange: (v: string) => void;
  onClear?: () => void;
  placeholder?: string;
};

export function FindBar({ value, onChange, onClear, placeholder }: Props) {
  return (
    <div
      className="omnix-glass flex w-full max-w-2xl items-center gap-2.5 rounded-full border border-omnix-accent-indigo/20 px-3 py-1.5 shadow-omnix-glow"
      id="search-panel"
      data-testid="find-bar"
    >
      <span
        className="shrink-0 font-display text-[10px] font-bold tracking-[0.2em] text-omnix-accent-indigo"
        id="search-label"
      >
        ASK BRAIN
      </span>
      <input
        id="search-input"
        className="min-w-0 flex-1 rounded-lg border border-slate-400/20 bg-[rgba(2,6,23,0.65)] px-2 py-1.5 font-mono text-sm text-slate-100 transition-[border-color,box-shadow] focus:border-omnix-accent-indigo/65 focus:shadow-[0_0_18px_rgba(99,102,241,0.22)] focus:outline-none placeholder:text-omnix-text-dim"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder ?? "symbol, file, path…"}
        type="search"
        autoComplete="off"
        spellCheck={false}
      />
      {value && onClear && (
        <button
          type="button"
          className="flex h-7 min-w-7 cursor-pointer items-center justify-center rounded-lg border border-slate-400/15 bg-[rgba(2,6,23,0.45)] text-slate-400 text-base leading-none transition-colors hover:border-omnix-accent-indigo/35 hover:text-slate-200"
          title="Clear"
          aria-label="Clear"
          onClick={onClear}
        >
          ✕
        </button>
      )}
    </div>
  );
}
