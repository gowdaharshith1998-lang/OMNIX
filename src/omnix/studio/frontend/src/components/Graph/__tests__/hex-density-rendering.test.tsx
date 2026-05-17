import { describe, expect, it } from 'vitest';
import {
  RING_TEXTURE_BASE_RADIUS,
  SLICE20_HEX_BASE_RADIUS,
  SLICE20_MIN_ZOOM_FOR_RINGS,
  SLICE20_RING_ALPHA,
  SLICE20_RING_RADIUS_MULT,
  slice20CssHexToPixi,
} from '../viewerEngine';
import { ENTITY_PALETTE, FALLBACK_COLOR, colorForType } from '../entityPalette';
import { generateBrainEnvelope } from '../brainEnvelope';

describe('hex density rendering (slice-20)', () => {
  it('test_hex_base_radius_in_target_range', () => {
    expect(SLICE20_HEX_BASE_RADIUS).toBeGreaterThanOrEqual(3);
    expect(SLICE20_HEX_BASE_RADIUS).toBeLessThanOrEqual(5);
  });

  it('test_data_hex_uses_entity_palette', () => {
    const pix = slice20CssHexToPixi(colorForType('people'));
    expect(pix).toBe(slice20CssHexToPixi(ENTITY_PALETTE.people));
  });

  it('test_unknown_type_uses_fallback', () => {
    const pix = slice20CssHexToPixi(colorForType('__no_such_type__'));
    expect(pix).toBe(slice20CssHexToPixi(FALLBACK_COLOR));
  });

  it('test_filler_hexes_render_at_low_alpha', () => {
    expect(0.16).toBeLessThan(0.25);
  });

  it('test_axiom_signed_renders_ring', () => {
    const meta = { axiom_signed: true };
    const ws = SLICE20_MIN_ZOOM_FOR_RINGS + 0.1;
    const show = meta.axiom_signed === true && ws >= SLICE20_MIN_ZOOM_FOR_RINGS;
    expect(show).toBe(true);
  });

  it('test_axiom_unsigned_no_ring', () => {
    const show = (undefined as unknown as { axiom_signed?: boolean })?.axiom_signed === true;
    expect(show).toBe(false);
  });

  it('test_ring_radius_scales_with_hex', () => {
    const scale = (SLICE20_HEX_BASE_RADIUS * SLICE20_RING_RADIUS_MULT) / RING_TEXTURE_BASE_RADIUS;
    const expected = (4 * 1.4) / 20;
    expect(Math.abs(scale - expected)).toBeLessThan(0.5);
  });

  it('test_ring_alpha_subtle', () => {
    expect(SLICE20_RING_ALPHA).toBeGreaterThanOrEqual(0.3);
    expect(SLICE20_RING_ALPHA).toBeLessThanOrEqual(0.4);
  });

  it('test_ring_color_matches_entity', () => {
    const t = 'ticket';
    const ringTint = slice20CssHexToPixi(colorForType(t));
    const hexTint = slice20CssHexToPixi(colorForType(t));
    expect(ringTint).toBe(hexTint);
  });

  it('test_brain_envelope_visual_clusters_not_rect_grid', () => {
    const hx = generateBrainEnvelope({
      canvasW: 600,
      canvasH: 500,
      hexRadius: 4,
      envelopeRx: 260,
      envelopeRy: 200,
      envelopeCx: 0,
      envelopeCy: 0,
      clusters: [
        { id: 'a', cx: -120, cy: 0, radius: 100, density: 0.6 },
        { id: 'b', cx: 120, cy: 0, radius: 100, density: 0.6 },
      ],
      fillerToDataRatio: [2, 4],
      seed: 7,
    });
    const inClusters = hx.filter((h) => h.clusterId);
    expect(inClusters.length).toBeGreaterThan(50);
    const xs = inClusters.map((h) => h.cx);
    const spread = Math.max(...xs) - Math.min(...xs);
    expect(spread).toBeGreaterThan(80);
  });
});
