type Props = {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
};

export function FindBar({ value, onChange, placeholder }: Props) {
  return (
    <div className="flex w-full max-w-2xl items-center gap-2 rounded-md border border-studio-line bg-black/30 px-3 py-1.5">
      <span className="text-studio-muted" aria-hidden>
        ⌕
      </span>
      <input
        className="min-w-0 flex-1 bg-transparent text-sm text-slate-100 outline-none placeholder:text-slate-600"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder ?? "Filter in project…"}
        type="search"
        spellCheck={false}
      />
    </div>
  );
}
