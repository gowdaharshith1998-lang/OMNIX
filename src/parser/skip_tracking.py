"""Aggregate skip stats for analyze trust / coverage reporting."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from src.graph.store import GraphStore
from src.parser.grammar_detect import SUGGESTED_INSTALL, grammar_for_extension


def _est_lines_from_size(size: int) -> int:
    """Cheap LOC proxy from file size (no extra reads). ~45 bytes/line typical."""
    if size <= 0:
        return 0
    return max(1, size // 45)


def line_count_utf8(text: str) -> int:
    if not text:
        return 0
    n = text.count("\n")
    return n if text.endswith("\n") else n + 1


@dataclass
class SkipAggregate:
    """Per-(extension, reason) buckets; parsed LOC for coverage ratio."""

    files: defaultdict[tuple[str, str], int] = field(
        default_factory=lambda: defaultdict(int)
    )
    loc_est: defaultdict[tuple[str, str], int] = field(
        default_factory=lambda: defaultdict(int)
    )
    parsed_loc: int = 0
    n_parsed_files: int = 0
    has_no_grammar: bool = False

    def record_skip(
        self,
        extension: str,
        reason: str,
        size: int,
        *,
        grammar_name: str | None = None,
    ) -> None:
        key = (extension, reason)
        self.files[key] += 1
        self.loc_est[key] += _est_lines_from_size(size)
        if reason == "no_grammar":
            self.has_no_grammar = True
        _ = grammar_name  # reserved for future per-row hints

    def record_too_large(self, extension: str, size: int) -> None:
        self.record_skip(extension, "too_large", size)

    def add_parsed(self, text: str) -> None:
        self.parsed_loc += line_count_utf8(text)
        self.n_parsed_files += 1

    @property
    def n_files_skipped(self) -> int:
        return int(sum(self.files.values()))

    @property
    def skipped_est_loc(self) -> int:
        return int(sum(self.loc_est.values()))

    def db_rows(self) -> list[tuple[str, int, int, str, str | None]]:
        rows: list[tuple[str, int, int, str, str | None]] = []
        for (ext, reason), nf in sorted(self.files.items()):
            loc = int(self.loc_est[(ext, reason)])
            sug: str | None = None
            if reason == "no_grammar":
                g = grammar_for_extension(ext)
                if g:
                    sug = SUGGESTED_INSTALL.get(g)
            rows.append((ext, nf, loc, reason, sug))
        return rows

    def persist(self, store: GraphStore) -> None:
        store.replace_skip_summary(self.db_rows())


def exit_code_for_skips(
    *,
    strict: bool,
    ratio_threshold: float,
    agg: SkipAggregate,
) -> int:
    """
    Exit 2 if (strict and any no_grammar skip) OR (skipped_est / total > ratio_threshold).
    *ratio_threshold* is already resolved (--strict implies 0.5 unless user lowered).
    """
    skipped = agg.skipped_est_loc
    parsed = agg.parsed_loc
    total = skipped + parsed
    rc = 0
    if strict and agg.has_no_grammar:
        rc = 2
    if total > 0 and skipped / total > ratio_threshold:
        rc = 2
    return rc


def format_skip_banner(agg: SkipAggregate) -> str | None:
    if agg.n_files_skipped <= 0:
        return None
    merged: dict[str, dict[str, object]] = {}
    for (ext, reason), nf in agg.files.items():
        loc = int(agg.loc_est[(ext, reason)])
        bucket = merged.setdefault(
            ext,
            {"files": 0, "loc": 0, "reasons": set()},
        )
        bucket["files"] = int(bucket["files"]) + nf  # type: ignore[operator]
        bucket["loc"] = int(bucket["loc"]) + loc  # type: ignore[operator]
        cast_set = bucket["reasons"]
        assert isinstance(cast_set, set)
        cast_set.add(reason)

    items = sorted(merged.items(), key=lambda kv: int(kv[1]["loc"]), reverse=True)  # type: ignore[arg-type]
    top = items[:5]
    rest = items[5:]

    skipped_files = agg.n_files_skipped
    skipped_loc = agg.skipped_est_loc
    lines: list[str] = [
        f"⚠️  Skipped {skipped_files:,} files (~{skipped_loc:,} est. LOC from size) — coverage gaps:"
    ]

    def _reason_label(ext: str, reasons: set[str]) -> tuple[str, str | None]:
        if "no_grammar" in reasons:
            g = grammar_for_extension(ext)
            hint = SUGGESTED_INSTALL.get(g, "") if g else ""
            tail = "grammar not installed"
            return tail, (hint or None)
        if "binary" in reasons:
            return "binary file", None
        if "too_large" in reasons:
            return "file over size cap", None
        if "unknown_extension" in reasons:
            return "no grammar mapped", None
        return "skipped", None

    for ext, data in top:
        reasons_set = data["reasons"]
        assert isinstance(reasons_set, set)
        nf = int(data["files"])
        loc = int(data["loc"])
        label, install = _reason_label(ext, reasons_set)
        pad = max(0, 7 - len(ext))
        ext_col = f"{ext}{' ' * pad}"
        lines.append(f"   {ext_col} ({nf:,} files, {loc:,} est. LOC) — {label}")
        if install:
            lines.append(f"{' ' * 11}install: {install}")

    if rest:
        more_n = len(rest)
        more_files = sum(int(d["files"]) for _, d in rest)  # type: ignore[misc]
        more_loc = sum(int(d["loc"]) for _, d in rest)  # type: ignore[misc]
        lines.append(
            f"   ...and {more_n} more extensions ({more_files:,} files, {more_loc:,} est. LOC)."
        )

    return "\n".join(lines)
