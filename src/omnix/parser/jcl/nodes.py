"""JCL node dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class JclDd:
    name: str
    raw: str


@dataclass(frozen=True)
class JclStep:
    name: str
    exec_pgm: str | None
    dds: tuple[JclDd, ...] = ()
    raw: str = ""
    unparsed: bool = False


@dataclass(frozen=True)
class JclProc:
    name: str


@dataclass(frozen=True)
class JclJob:
    name: str
    steps: tuple[JclStep, ...] = ()
    procs: tuple[JclProc, ...] = ()
    metadata: dict[str, str] = field(default_factory=dict)
