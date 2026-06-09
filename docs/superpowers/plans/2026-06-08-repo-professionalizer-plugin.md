# Repo Professionalizer Plugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Install a personal Codex plugin named `repo-professionalizer` that runs a gated multi-agent workflow for professional repository cleanup.

**Architecture:** Use the plugin creator scaffold for the manifest, personal marketplace entry, skills, scripts, and assets. Replace generated starter files with review-gated workflow skills, deterministic inventory scripts, and reusable markdown templates.

**Tech Stack:** Codex plugin manifest JSON, Codex skills, Python 3 scripts, Markdown templates, personal Codex marketplace.

---

### Task 1: Scaffold Plugin

**Files:**
- Create: `C:\Users\HG\plugins\repo-professionalizer\.codex-plugin\plugin.json`
- Create: `C:\Users\HG\plugins\repo-professionalizer\skills`
- Create: `C:\Users\HG\plugins\repo-professionalizer\scripts`
- Create: `C:\Users\HG\plugins\repo-professionalizer\assets`
- Modify: `C:\Users\HG\.agents\plugins\marketplace.json`

- [ ] **Step 1: Run plugin creator scaffold**

Run:

```powershell
& 'C:\Users\HG\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' 'C:\Users\HG\.codex\skills\.system\plugin-creator\scripts\create_basic_plugin.py' repo-professionalizer --with-skills --with-scripts --with-assets --with-marketplace
```

Expected: creates `C:\Users\HG\plugins\repo-professionalizer` and adds the plugin to the personal marketplace.

### Task 2: Write Manifest Metadata

**Files:**
- Modify: `C:\Users\HG\plugins\repo-professionalizer\.codex-plugin\plugin.json`

- [ ] **Step 1: Replace scaffold defaults**

Write manifest metadata with name `repo-professionalizer`, version `0.1.0`, skills path `./skills/`, category `Productivity`, and clear interface copy for a gated multi-agent repo cleanup plugin.

- [ ] **Step 2: Validate manifest**

Run:

```powershell
& 'C:\Users\HG\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' 'C:\Users\HG\.codex\skills\.system\plugin-creator\scripts\validate_plugin.py' 'C:\Users\HG\plugins\repo-professionalizer'
```

Expected: validation passes.

### Task 3: Write Skills

**Files:**
- Create: `C:\Users\HG\plugins\repo-professionalizer\skills\repo-professionalizer\SKILL.md`
- Create: `C:\Users\HG\plugins\repo-professionalizer\skills\repo-audit\SKILL.md`
- Create: `C:\Users\HG\plugins\repo-professionalizer\skills\docs-professionalizer\SKILL.md`
- Create: `C:\Users\HG\plugins\repo-professionalizer\skills\repo-organization\SKILL.md`
- Create: `C:\Users\HG\plugins\repo-professionalizer\skills\refactor-execute\SKILL.md`
- Create: `C:\Users\HG\plugins\repo-professionalizer\skills\github-finish\SKILL.md`

- [ ] **Step 1: Add coordinator skill**

Write the main skill with Gate 0 through Gate 7, coordinator responsibilities, multi-agent boundaries, and stop conditions.

- [ ] **Step 2: Add specialist skills**

Write the five specialist skills with narrow responsibilities, required artifacts, and review-gate behavior.

### Task 4: Write Scripts

**Files:**
- Create: `C:\Users\HG\plugins\repo-professionalizer\scripts\repo_inventory.py`
- Create: `C:\Users\HG\plugins\repo-professionalizer\scripts\docs_inventory.py`
- Create: `C:\Users\HG\plugins\repo-professionalizer\scripts\write_gate_artifact.py`

- [ ] **Step 1: Add repo inventory script**

Implement a read-only scanner that reports branch, remotes, dirty files, language markers, package files, docs, and likely test commands as JSON.

- [ ] **Step 2: Add docs inventory script**

Implement a read-only scanner that reports README/docs files, headings, stale markers, duplicate titles, and missing top headings as JSON.

- [ ] **Step 3: Add gate artifact writer**

Implement a helper that writes timestamped markdown gate artifacts under `.codex/repo-professionalizer/runs/<timestamp>/`.

- [ ] **Step 4: Smoke test scripts**

Run each script with `--help` and run both scanners against `C:\Users\HG\Documents\omnix`.

### Task 5: Write Templates and Validate Install

**Files:**
- Create: `C:\Users\HG\plugins\repo-professionalizer\assets\templates\audit-report.md`
- Create: `C:\Users\HG\plugins\repo-professionalizer\assets\templates\docs-plan.md`
- Create: `C:\Users\HG\plugins\repo-professionalizer\assets\templates\refactor-plan.md`
- Create: `C:\Users\HG\plugins\repo-professionalizer\assets\templates\gate-summary.md`
- Create: `C:\Users\HG\plugins\repo-professionalizer\assets\templates\pr-description.md`

- [ ] **Step 1: Add markdown templates**

Write concise templates for audit reports, docs plans, refactor plans, gate summaries, and pull request descriptions.

- [ ] **Step 2: Validate plugin**

Run:

```powershell
& 'C:\Users\HG\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' 'C:\Users\HG\.codex\skills\.system\plugin-creator\scripts\validate_plugin.py' 'C:\Users\HG\plugins\repo-professionalizer'
```

Expected: validation passes.

- [ ] **Step 3: Confirm marketplace entry**

Read `C:\Users\HG\.agents\plugins\marketplace.json` and confirm the plugin entry includes `policy.installation`, `policy.authentication`, and `category`.
