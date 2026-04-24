import { describe, it, expect, vi, beforeEach } from 'vitest';
import { resetAllVault } from './helpers.js';
import { createVault } from '../../src/web/vault/vault.js';

vi.mock('../../src/web/vault/validators.js', () => ({
  validateProviderKey: vi.fn(() => Promise.resolve({ ok: true })),
}));

describe('routing', () => {
  beforeEach(async () => {
    await resetAllVault();
  });

  it('assign, getRoute, reassign', async () => {
    const v = createVault();
    await v.init('routing_init_12');
    const a = await v.addKey({
      provider: 'openai',
      label: 'a',
      key_value: 'sk-routing-test-key-abcdefghij',
    });
    expect(a.ok).toBe(true);
    if (!a.ok) return;
    const kid = a.key.id;
    await v.assignAgent('agent-1', kid);
    const r1 = await v.getRoute('agent-1');
    expect(r1).toEqual({ key_id: kid, provider: 'openai' });
    const b = await v.addKey({
      provider: 'anthropic',
      label: 'b',
      key_value: 'sk-ant-routing-test-key-abcdefgh',
    });
    expect(b.ok).toBe(true);
    if (!b.ok) return;
    await v.assignAgent('agent-1', b.key.id);
    const r2 = await v.getRoute('agent-1');
    expect(r2?.key_id).toBe(b.key.id);
  });

  it('getProviderKeyForAgent returns plaintext when unlocked', async () => {
    const v = createVault();
    await v.init('prov_key_test_12');
    const a = await v.addKey({
      provider: 'openai',
      label: 'x',
      key_value: 'unique_plaintext_key_value_123',
    });
    expect(a.ok).toBe(true);
    if (!a.ok) return;
    await v.assignAgent('agx', a.key.id);
    const pk = await v.getProviderKeyForAgent('agx');
    expect(pk).not.toBeNull();
    if (pk) {
      expect(pk.plaintext_key).toBe('unique_plaintext_key_value_123');
      expect(pk.provider).toBe('openai');
    }
  });

  it('getProviderKeyForAgent returns null when locked', async () => {
    const v = createVault();
    await v.init('lock_route_12');
    const a = await v.addKey({
      provider: 'openai',
      label: 'x',
      key_value: 'sk-lock-route-test-key-abcdefgh',
    });
    expect(a.ok).toBe(true);
    if (!a.ok) return;
    await v.assignAgent('a', a.key.id);
    v.lock();
    const pk = await v.getProviderKeyForAgent('a');
    expect(pk).toBeNull();
  });

  it('getProviderKeyForAgent null when no route', async () => {
    const v = createVault();
    await v.init('no_route___12');
    const pk = await v.getProviderKeyForAgent('missing');
    expect(pk).toBeNull();
  });
});
