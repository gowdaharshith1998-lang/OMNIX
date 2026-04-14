"""OMNIX Agent Orchestrator — routes tasks to specialized agents."""

from __future__ import annotations

import json
import os

from .llm_router import LLMRouter
from .memory import AgentMemory
from .tools import OmnixTools


class AgentOrchestrator:
    """Coordinates specialized agents for code analysis."""

    def __init__(self, project_path: str, db_path: str = "omnix.db") -> None:
        self.project_path = project_path
        self.llm = LLMRouter()
        self.tools = OmnixTools(project_path, db_path)
        self.memory = AgentMemory()
        self.codebase_id = os.path.basename(os.path.abspath(project_path))

    @property
    def available(self) -> bool:
        return self.llm.available

    @property
    def provider_info(self) -> str:
        return self.llm.info

    def _trace_root_for_directory(self, dir_path: str) -> str:
        """Pick a graph node id in or under dir_path for edge tracing."""
        norm = dir_path.rstrip("/")
        graph_results = self.tools.search_graph(norm or "", limit=30)
        for node in graph_results.get("results", []):
            fp = node.get("file") or ""
            if isinstance(fp, str):
                if fp == norm or (norm and fp.startswith(norm + "/")):
                    nid = node.get("id")
                    if nid:
                        return str(nid)
        for node in graph_results.get("results", []):
            nid = node.get("id")
            if nid:
                return str(nid)
        return dir_path

    def diagnose(
        self, dir_path: str, issue_description: str | None = None
    ) -> dict[str, object]:
        """Run the debugger agent on a directory."""
        diagnostics = self.tools.get_diagnostics(dir_path)
        trace_root = self._trace_root_for_directory(dir_path)
        connections = self.tools.trace_connections(trace_root, depth=1)

        similar = self.memory.find_similar(
            self.codebase_id, issue_description or "general"
        )
        memory_context = ""
        if similar:
            memory_context = "\n\nPAST SIMILAR DIAGNOSES (learn from these):\n"
            for s in similar[:3]:
                memory_context += (
                    f"- Root cause: {s['root_cause']}, Fix: {s['fix']}, "
                    f"Was correct: {s['was_correct']}\n"
                )

        file_contents: list[str] = []
        graph_results = self.tools.search_graph(dir_path, limit=10)
        files_read: set[str] = set()
        for node in graph_results.get("results", []):
            fp = node.get("file")
            if fp and fp not in files_read and len(files_read) < 5:
                content = self.tools.read_file(str(fp))
                if "content" in content:
                    file_contents.append(
                        f"--- {fp} ---\n{str(content['content'])[:2000]}"
                    )
                    files_read.add(str(fp))

        system_prompt = """You are OMNIX AI — an expert code diagnostic agent. You analyze codebases using a knowledge graph that maps every function, class, import, and call relationship.

You have access to these facts about the code:
- The knowledge graph shows WHO calls WHOM, WHO imports WHOM
- "ENTANGLED" pairs are files that MUST change together (change one → break the other)
- "DARK_FORCE" connections are invisible dependencies (env vars, config, middleware)
- Circular imports mean two files import each other — fragile coupling

Your job:
1. Analyze the diagnostic data and source code provided
2. Identify the ROOT CAUSE of any issues (not just symptoms)
3. Explain WHY it's a problem in plain English
4. Suggest 2-3 SPECIFIC fixes with actual code changes
5. Rate your confidence (0-100%)

Format your response as JSON:
{
  "diagnosis": {
    "summary": "One sentence summary",
    "root_cause": "Detailed explanation of the root cause",
    "severity": "high|medium|low",
    "confidence": 85
  },
  "affected_files": ["file1.py", "file2.py"],
  "fixes": [
    {
      "title": "Short title",
      "description": "What this fix does",
      "code_changes": "Specific code to change (use diff format if possible)",
      "risk": "low|medium|high",
      "effort": "5min|30min|1hr|1day"
    }
  ],
  "reasoning_steps": [
    "Step 1: I noticed X in the graph data",
    "Step 2: I read file Y and found Z",
    "Step 3: This means..."
  ]
}"""

        user_prompt = f"""Analyze this module and diagnose any issues:

DIRECTORY: {dir_path}
DIAGNOSTICS: {json.dumps(diagnostics, indent=2)}
CONNECTIONS (depth 1, from node {trace_root}): {json.dumps(connections.get("trace", [])[:30], indent=2)}
{memory_context}

SOURCE FILES:
{chr(10).join(file_contents[:3])}

{f"SPECIFIC ISSUE TO INVESTIGATE: {issue_description}" if issue_description else "Find and diagnose all issues in this module."}

Respond with JSON only. No markdown backticks."""

        response = self.llm.chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
        )

        if "error" in response:
            return {"error": response["error"]}

        try:
            content = response["content"].strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1]
                if content.endswith("```"):
                    content = content[:-3]
            result = json.loads(content)
            result["provider"] = response.get("provider", "unknown")
        except (json.JSONDecodeError, ValueError, KeyError):
            result = {
                "diagnosis": {
                    "summary": response["content"][:500],
                    "confidence": 50,
                },
                "fixes": [],
                "reasoning_steps": ["Raw response — JSON parsing failed"],
                "provider": response.get("provider", "unknown"),
                "raw": True,
            }

        diag = result.get("diagnosis")
        if not isinstance(diag, dict):
            diag = {}
        fixes = result.get("fixes")
        if not isinstance(fixes, list):
            fixes = []
        self.memory.store_diagnosis(
            self.codebase_id,
            dir_path,
            issue_description or "general",
            str(diag.get("root_cause", "")),
            json.dumps(fixes[:1]),
            float(diag.get("confidence", 0) or 0),
            str(result.get("provider", "unknown")),
        )

        return result

    def security_scan(self, dir_path: str | None = None) -> dict[str, object]:
        """Run security agent on a directory or full codebase."""
        target = dir_path or "."
        diagnostics = self.tools.get_diagnostics(target)

        graph_results = self.tools.search_graph(target, limit=20)
        file_contents: list[str] = []
        files_read: set[str] = set()
        for node in graph_results.get("results", []):
            fp = node.get("file")
            if fp and fp not in files_read and len(files_read) < 8:
                content = self.tools.read_file(str(fp))
                if "content" in content:
                    file_contents.append(
                        f"--- {fp} ---\n{str(content['content'])[:1500]}"
                    )
                    files_read.add(str(fp))

        system_prompt = """You are OMNIX Security Agent — an expert cybersecurity auditor for codebases.
Scan the provided code for OWASP Top 10 vulnerabilities, auth issues, injection vectors, hardcoded secrets, SSRF, IDOR, and missing security controls.

Format response as JSON:
{
  "scan_summary": "Overall security assessment",
  "risk_level": "critical|high|medium|low",
  "vulnerabilities": [
    {
      "type": "OWASP category",
      "severity": "critical|high|medium|low",
      "file": "filename.py",
      "line": 42,
      "description": "What's wrong",
      "fix": "How to fix it",
      "cwe": "CWE-XXX"
    }
  ],
  "positive_findings": ["Good security practices found"]
}"""

        user_prompt = f"""Security scan this codebase section:

DIRECTORY: {target}
DIAGNOSTICS: {json.dumps(diagnostics, indent=2)}

SOURCE FILES:
{chr(10).join(file_contents)}

Find ALL security vulnerabilities. Be thorough. Respond with JSON only."""

        response = self.llm.chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
        )

        if "error" in response:
            return {"error": response["error"]}

        try:
            content = response["content"].strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1]
                if content.endswith("```"):
                    content = content[:-3]
            result = json.loads(content)
            result["provider"] = response.get("provider", "unknown")
        except (json.JSONDecodeError, ValueError, KeyError):
            result = {
                "scan_summary": response["content"][:500],
                "vulnerabilities": [],
                "provider": response.get("provider", "unknown"),
                "raw": True,
            }

        return result

    def explain_architecture(self) -> dict[str, object]:
        """Architect agent — explain the codebase to a new developer."""
        graph_results = self.tools.search_graph("", limit=50)

        system_prompt = """You are OMNIX Architect Agent — you explain codebase architecture clearly.
Given knowledge graph data about a codebase, provide a clear architectural overview.

Format response as JSON:
{
  "summary": "2-3 sentence overview",
  "main_modules": [
    {"name": "module name", "purpose": "what it does", "importance": "critical|high|medium|low"}
  ],
  "data_flow": "How data flows through the system",
  "tech_debt": ["Key tech debt items"],
  "onboarding_order": ["Read these files in this order to understand the codebase"],
  "risks": ["Top architectural risks"]
}"""

        user_prompt = f"""Explain this codebase architecture:

CODEBASE: {self.codebase_id}
GRAPH STATS: {json.dumps(graph_results, indent=2)}

Provide a clear, actionable architectural overview. Respond with JSON only."""

        response = self.llm.chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
        )

        if "error" in response:
            return {"error": response["error"]}

        try:
            content = response["content"].strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1]
                if content.endswith("```"):
                    content = content[:-3]
            out = json.loads(content)
            out["provider"] = response.get("provider", "unknown")
            return out
        except (json.JSONDecodeError, ValueError, KeyError):
            return {
                "summary": response["content"][:500],
                "provider": response.get("provider", "unknown"),
                "raw": True,
            }

    def ask(
        self, question: str, dir_path: str | None = None
    ) -> dict[str, object]:
        """Free-form question about the codebase."""
        context = ""
        if dir_path:
            diagnostics = self.tools.get_diagnostics(dir_path)
            trace_root = self._trace_root_for_directory(dir_path)
            connections = self.tools.trace_connections(trace_root, depth=1)
            context = (
                f"\nDIRECTORY CONTEXT:\n{json.dumps(diagnostics, indent=2)}\n"
                f"CONNECTIONS (from {trace_root}):\n"
                f"{json.dumps(connections.get('trace', [])[:20], indent=2)}"
            )

        system_prompt = f"""You are OMNIX AI — a code intelligence assistant with access to a knowledge graph of {self.codebase_id}.
The graph maps every function, class, import, and call relationship.
Answer questions about the codebase accurately and concisely.
If you're unsure, say so. If you need more context, say what you'd need."""

        response = self.llm.chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"{question}{context}"},
            ],
            temperature=0.3,
        )

        if "error" in response:
            return {"error": response["error"]}

        return {
            "answer": response.get("content", ""),
            "provider": response.get("provider", "unknown"),
        }
