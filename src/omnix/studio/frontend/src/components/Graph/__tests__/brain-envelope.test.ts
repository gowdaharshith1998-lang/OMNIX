import { describe, expect, it } from 'vitest';
import {
  generateBrainEnvelope,
  insideEllipse,
  neighborOffsets,
  type EnvelopeSpec,
} from '../brainEnvelope';

const baseSpec = (): EnvelopeSpec => ({
  canvasW: 800,
  canvasH: 600,
  hexRadius: 4,
  envelopeRx: 350,
  envelopeRy: 260,
  envelopeCx: 400,
  envelopeCy: 300,
  clusters: [
    { id: 'billing', cx: 300, cy: 240, radius: 110, density: 0.75 },
    { id: 'auth', cx: 520, cy: 260, radius: 95, density: 0.8 },
    { id: 'onboarding', cx: 400, cy: 360, radius: 100, density: 0.72 },
    { id: 'infra', cx: 260, cy: 400, radius: 90, density: 0.78 },
    { id: 'sales', cx: 540, cy: 410, radius: 85, density: 0.7 },
  ],
  fillerToDataRatio: [2, 4],
  seed: 42,
});

describe('brainEnvelope', () => {
  it('test_envelope_returns_hexes_inside_ellipse', () => {
    const spec = baseSpec();
    const hexes = generateBrainEnvelope(spec);
    expect(hexes.length).toBeGreaterThan(10);
    for (const h of hexes) {
      expect(
        insideEllipse(h.cx, h.cy, spec.envelopeCx, spec.envelopeCy, spec.envelopeRx, spec.envelopeRy),
      ).toBe(true);
    }
  });

  it('test_envelope_data_hexes_in_clusters', () => {
    const spec = baseSpec();
    const hexes = generateBrainEnvelope(spec);
    const dataInCluster = hexes.filter((h) => h.isData && h.clusterId);
    expect(dataInCluster.length).toBeGreaterThan(0);
    for (const h of dataInCluster) {
      const cl = spec.clusters.find((c) => c.id === h.clusterId);
      expect(cl).toBeDefined();
      const dx = h.cx - cl!.cx;
      const dy = h.cy - cl!.cy;
      expect(Math.sqrt(dx * dx + dy * dy)).toBeLessThanOrEqual(cl!.radius + 1);
    }
  });

  it('test_envelope_filler_hexes_outside_clusters', () => {
    const spec = baseSpec();
    const hexes = generateBrainEnvelope(spec);
    const fillerOutside = hexes.filter((h) => !h.isData && !h.clusterId);
    expect(fillerOutside.length).toBeGreaterThan(0);
  });

  it('test_envelope_filler_outnumbers_data_2_to_4x', () => {
    const spec = baseSpec();
    const hexes = generateBrainEnvelope(spec);
    const d = hexes.filter((h) => h.isData).length;
    const f = hexes.filter((h) => !h.isData).length;
    expect(d).toBeGreaterThan(0);
    const ratio = f / d;
    expect(ratio).toBeGreaterThanOrEqual(2);
    expect(ratio).toBeLessThanOrEqual(4);
  });

  it('test_envelope_six_neighbor_adjacency', () => {
    const spec = baseSpec();
    const hexes = generateBrainEnvelope(spec);
    const interior = hexes.find((h) => h.neighbors.length === 6);
    expect(interior).toBeDefined();
    const boundary = hexes.find((h) => h.neighbors.length > 0 && h.neighbors.length < 6);
    expect(boundary).toBeDefined();
  });

  it('test_envelope_adjacency_reciprocal', () => {
    const spec = baseSpec();
    const hexes = generateBrainEnvelope(spec);
    const byId = new Map(hexes.map((h) => [h.id, h]));
    for (const h of hexes) {
      for (const nid of h.neighbors) {
        const n = byId.get(nid);
        expect(n).toBeDefined();
        expect(n!.neighbors).toContain(h.id);
      }
    }
  });

  it('test_envelope_no_overlapping_hexes', () => {
    const spec = baseSpec();
    const hexes = generateBrainEnvelope(spec);
    const minNeighbor = Math.sqrt(3) * spec.hexRadius * 0.94;
    for (const h of hexes) {
      for (const nid of h.neighbors) {
        const o = hexes.find((x) => x.id === nid);
        expect(o).toBeDefined();
        const dist = Math.hypot(h.cx - o!.cx, h.cy - o!.cy);
        expect(dist).toBeGreaterThanOrEqual(minNeighbor - 0.05);
      }
    }
  });

  it('test_envelope_deterministic_for_same_seed', () => {
    const spec = baseSpec();
    const a = generateBrainEnvelope(spec);
    const b = generateBrainEnvelope(spec);
    expect(a.length).toBe(b.length);
    for (let i = 0; i < a.length; i++) {
      expect(a[i].id).toBe(b[i].id);
      expect(a[i].isData).toBe(b[i].isData);
      expect(a[i].cx).toBe(b[i].cx);
    }
  });
});
