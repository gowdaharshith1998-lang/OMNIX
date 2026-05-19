"""Line-based JCL parser with graph emission."""

from __future__ import annotations

import re

from omnix.graph.store import GraphStore
from omnix.parser.jcl.nodes import JclDd, JclJob, JclProc, JclStep
from omnix.parser.memory_graph import MemoryGraphStore

_GraphSink = GraphStore | MemoryGraphStore

_JOB_RE = re.compile(r"^//([^\s]+)\s+JOB\b", re.IGNORECASE)
_STEP_RE = re.compile(r"^//([^\s]+)\s+EXEC\s+PGM=([^,\s]+)", re.IGNORECASE)
_DD_RE = re.compile(r"^//([^\s]+)\s+DD\b", re.IGNORECASE)
_PROC_RE = re.compile(r"^//([^\s]+)\s+PROC\b", re.IGNORECASE)


def _normalize_continuations(lines: list[str]) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if len(line) >= 72 and line[71] not in (" ", "") and i + 1 < len(lines):
            out.append(line[:71] + lines[i + 1].lstrip())
            i += 2
            continue
        out.append(line)
        i += 1
    return out


def parse_jcl_text(rel_path: str, text: str, store: _GraphSink | None = None) -> JclJob:
    lines = _normalize_continuations(text.splitlines())
    job_name = "UNKNOWN"
    steps: list[JclStep] = []
    procs: list[JclProc] = []
    cur_dds: list[JclDd] = []
    cur_step_idx: int | None = None

    for raw in lines:
        raw2 = raw.rstrip("\n")
        m_job = _JOB_RE.match(raw2)
        if m_job:
            job_name = m_job.group(1)
            continue
        m_proc = _PROC_RE.match(raw2)
        if m_proc:
            procs.append(JclProc(name=m_proc.group(1)))
            continue
        m_step = _STEP_RE.match(raw2)
        if m_step:
            if cur_step_idx is not None:
                prev = steps[cur_step_idx]
                steps[cur_step_idx] = JclStep(
                    name=prev.name,
                    exec_pgm=prev.exec_pgm,
                    dds=tuple(cur_dds),
                    raw=prev.raw,
                    unparsed=prev.unparsed,
                )
            cur_dds = []
            steps.append(JclStep(name=m_step.group(1), exec_pgm=m_step.group(2), raw=raw2))
            cur_step_idx = len(steps) - 1
            continue
        m_dd = _DD_RE.match(raw2)
        if m_dd and cur_step_idx is not None:
            cur_dds.append(JclDd(name=m_dd.group(1), raw=raw2))
            continue
        if raw2.startswith("//") and cur_step_idx is not None:
            prev = steps[cur_step_idx]
            steps[cur_step_idx] = JclStep(
                name=prev.name,
                exec_pgm=prev.exec_pgm,
                dds=prev.dds,
                raw=raw2,
                unparsed=True,
            )

    if cur_step_idx is not None:
        prev = steps[cur_step_idx]
        steps[cur_step_idx] = JclStep(
            name=prev.name,
            exec_pgm=prev.exec_pgm,
            dds=tuple(cur_dds),
            raw=prev.raw,
            unparsed=prev.unparsed,
        )

    job = JclJob(name=job_name, steps=tuple(steps), procs=tuple(procs))
    if store is not None:
        _emit_jcl_graph(store, rel_path, text, job)
    return job


def _emit_jcl_graph(store: _GraphSink, rel_path: str, text: str, job: JclJob) -> None:
    lc = text.count("\n") + 1 if text else 1
    file_id = rel_path
    job_id = f"{rel_path}::JclJob::{job.name}"
    store.add_node(
        id=file_id,
        name=rel_path.rsplit("/", 1)[-1],
        type="file",
        file_path=rel_path,
        start_line=1,
        end_line=lc,
        complexity=lc,
        metadata={"language": "jcl"},
    )
    store.add_node(
        id=job_id,
        name=job.name,
        type="JclJob",
        file_path=rel_path,
        start_line=1,
        end_line=lc,
        complexity=lc,
        metadata={},
    )
    store.add_edge(file_id, job_id, "DEFINES")
    for i, step in enumerate(job.steps):
        sid = f"{job_id}::step::{i}::{step.name}"
        stype = "JclStepUnparsed" if step.unparsed else "JclStep"
        store.add_node(id=sid, name=step.name, type=stype, file_path=rel_path, complexity=1, metadata={"exec_pgm": step.exec_pgm})
        store.add_edge(job_id, sid, "DEFINES")
        if step.exec_pgm:
            pid = f"CobolProgram::{step.exec_pgm}"
            store.add_node(id=pid, name=step.exec_pgm, type="CobolProgram", metadata={})
            store.add_edge(sid, pid, "invokes")
        for dd in step.dds:
            did = f"{sid}::dd::{dd.name}"
            store.add_node(id=did, name=dd.name, type="JclDd", file_path=rel_path, complexity=1, metadata={"raw": dd.raw})
            store.add_edge(sid, did, "DEFINES")
    for proc in job.procs:
        pr_id = f"{job_id}::proc::{proc.name}"
        store.add_node(id=pr_id, name=proc.name, type="JclProc", file_path=rel_path, complexity=1, metadata={})
        store.add_edge(job_id, pr_id, "DEFINES")
