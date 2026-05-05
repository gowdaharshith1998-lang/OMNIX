/**
 * Mirrors tests/studio/test_naming_pivot.py — company-brain UI strings (slice-19).
 * File-level assertions only (no new test dependencies).
 */
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const _here = dirname(fileURLToPath(import.meta.url));
/** `src/studio/frontend/src` (`components/__tests__` → `..`/`..`) */
const frontendSrc = join(_here, '..', '..');
/** OMNIX repo root (`frontend/src` → …/omnix) */
const repoRoot = join(frontendSrc, '..', '..', '..', '..');
const readFE = (relFromSrc: string) => readFileSync(join(frontendSrc, relFromSrc), 'utf-8');
const readRoot = (rel: string) => readFileSync(join(repoRoot, rel), 'utf-8');

describe('naming pivot (slice-19)', () => {
  it('XRayHead — BRAIN, not X-RAY', () => {
    const t = readFE('components/XRayHead.tsx');
    expect(t).toContain('BRAIN');
    expect(t).not.toContain('X-RAY');
  });

  it('FindBar — ASK BRAIN', () => {
    const t = readFE('components/FindBar.tsx');
    expect(t).toContain('ASK BRAIN');
    expect(t).not.toContain('FIND');
  });

  it('XRayMetrics — Entities, Connections, Sources', () => {
    const t = readFE('components/XRayMetrics.tsx');
    expect(t).toContain('Entities');
    expect(t).toContain('Connections');
    expect(t).toContain('Sources');
    expect(t).not.toContain('Packages (tree)');
    expect(t).not.toContain('Call edges');
    expect(t).not.toContain('Import edges');
  });

  it('Workspace — data-omnix-brain + variant brain', () => {
    const t = readFE('components/Workspace.tsx');
    expect(t).toContain('data-omnix-brain="1"');
    expect(t).not.toContain('data-omnix-constellation="1"');
    expect(t).toContain('variant="brain"');
    expect(t).not.toContain('variant="constellation"');
  });

  it('StatsPanel — brain variant (no constellation substring)', () => {
    const t = readFE('components/StatsPanel.tsx');
    expect(t).toContain('"brain"');
    expect(t.toLowerCase()).not.toContain('constellation');
  });

  it('CodeTab empty state', () => {
    const t = readFE('components/CodeTab.tsx');
    expect(t).toContain('Select an entity in the brain');
    expect(t.toLowerCase()).not.toContain('constellation');
  });

  it('viewerEngine HTML', () => {
    const t = readFE('components/Graph/viewerEngine.ts');
    expect(t).toContain('BRAIN</div>');
    expect(t).toContain('BRAIN · ENTITY');
    expect(t).not.toContain('X-RAY</div>');
    expect(t).not.toContain('X-RAY · SYMBOL');
  });

  it('scopeRegistry — Workspace', () => {
    const t = readFE('store/scopeRegistry.ts');
    expect(t).toContain('label: "Workspace"');
    expect(t).not.toContain('label: "Repository"');
  });

  it('XRayTab default scope — Workspace', () => {
    const t = readFE('components/XRayTab.tsx');
    expect(t).toContain('name: "Workspace"');
    expect(t).not.toContain('name: "Repository"');
  });

  it('MCP server tool descriptions', () => {
    const t = readRoot('src/mcp/server.py');
    expect(t).toContain('knowledge graph');
    expect(t).not.toContain('code knowledge graph');
    expect(t).toContain('system health');
    expect(t).not.toContain('code health');
    expect(t).toContain('entity connections');
    expect(t).not.toContain('code connections');
  });

  it('CLI docstring', () => {
    const t = readRoot('src/cli.py');
    expect(t).toContain('knowledge intelligence and AXIOM provenance');
    expect(t).not.toContain('code intelligence and AXIOM provenance');
  });

  it('README opening', () => {
    const t = readRoot('README.md');
    expect(t).toContain(
      'open-core company brain — a visual knowledge graph that AI agents navigate to do work, with AXIOM cryptographic governance and Calibra confidence calibration',
    );
    expect(t).toContain('every entity, every relationship, every signed action');
    expect(t).not.toContain('open-core code intelligence product');
    expect(t).not.toContain('every file, function, class, and connection');
  });
});
