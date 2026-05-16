import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { generateBrainEnvelope } from '../brainEnvelope';

const _here = dirname(fileURLToPath(import.meta.url));
const viewerEnginePath = join(_here, '..', 'viewerEngine.ts');

describe('hex fps / ticker (slice-20)', () => {
  it('test_fps_floor_at_full_load', () => {
    /* Stress-sized envelope (not full 4.7k graph entities — those are sim nodes); measures pure tessellation + adjacency path for slice-20 regression. */
    const spec = {
      canvasW: 520,
      canvasH: 420,
      hexRadius: 4,
      envelopeRx: 240,
      envelopeRy: 190,
      envelopeCx: 0,
      envelopeCy: 0,
      clusters: [
        { id: 'billing', cx: -90, cy: -70, radius: 120, density: 0.52 },
        { id: 'auth', cx: 95, cy: -68, radius: 115, density: 0.53 },
        { id: 'onboarding', cx: 0, cy: 88, radius: 118, density: 0.51 },
        { id: 'infra', cx: -100, cy: 85, radius: 108, density: 0.52 },
        { id: 'sales', cx: 92, cy: 90, radius: 105, density: 0.5 },
      ],
      fillerToDataRatio: [2, 4] as [number, number],
      seed: 0x4758,
    };
    const t0 = performance.now();
    const frames = 24;
    for (let f = 0; f < frames; f++) {
      generateBrainEnvelope(spec);
    }
    const elapsed = performance.now() - t0;
    const mean = elapsed / frames;
    expect(mean).toBeLessThan(18.2);
  });

  it('test_no_double_ticker', () => {
    const src = readFileSync(viewerEnginePath, 'utf-8');
    const matches = src.match(/\.ticker\.add\(/g);
    expect(matches?.length).toBe(1);
  });
});
