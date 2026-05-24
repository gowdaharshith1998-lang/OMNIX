import { useEffect, useRef, useState } from "react";
import type { LanguageOption } from "./types";

type Props = {
  options: LanguageOption[];
  value: string;
  onChange: (id: string) => void;
  ariaLabel: string;
  size?: "sm" | "md";
  anchor?: "top" | "bottom";
};

export function LanguagePicker({
  options,
  value,
  onChange,
  ariaLabel,
  size = "md",
  anchor = "top",
}: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);
  const current = options.find((o) => o.id === value) ?? options[0];

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (!ref.current) return;
      if (!ref.current.contains(event.target as Node)) setOpen(false);
    };
    const esc = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("mousedown", close);
    window.addEventListener("keydown", esc);
    return () => {
      window.removeEventListener("mousedown", close);
      window.removeEventListener("keydown", esc);
    };
  }, [open]);

  return (
    <div className="m42-dropdown" ref={ref}>
      <button
        type="button"
        className="m42-dropdown-trigger"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={ariaLabel}
        onClick={() => setOpen((s) => !s)}
        style={size === "sm" ? { height: 24, padding: "0 8px", fontSize: 10 } : undefined}
      >
        <span>{current?.label ?? "—"}</span>
        <span className="m42-dropdown-caret">▾</span>
      </button>
      {open && current ? (
        <div
          className={`m42-dropdown-menu ${anchor === "top" ? "" : "m42-anchor-top"}`}
          role="listbox"
          aria-label={ariaLabel}
        >
          {options.map((option) => (
            <button
              key={option.id}
              type="button"
              role="option"
              aria-selected={option.id === value}
              className={`m42-dropdown-item ${option.id === value ? "is-active" : ""}`}
              onClick={() => {
                onChange(option.id);
                setOpen(false);
              }}
            >
              <span>{option.label}</span>
              <span className="m42-dropdown-item-hint">{option.hint}</span>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
