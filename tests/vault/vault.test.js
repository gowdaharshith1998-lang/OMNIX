import { describe, it, expect, vi, beforeEach } from 'vitest';
import { resetAllVault } from './helpers.js';
import { getRecord, putRecord, getAllFromStore, STORES } from '../../src/web/vault/storage.js';
import { base64ToBytes, bytesToBase64 } from '../../src/web/vault/crypto.js';
import { createVault } from '../../src/web/vault/vault.js';
import { validateProviderKey } from '../../src/web/vault/validators.js';

vi.mock('../../src/web/vault/validators.js', () => ({
  validateProviderKey: vi.fn(() => Promise.resolve({ ok: true })),
}));

describe('vault core', () => {
  beforeEach(async () => {
    await resetAllVault();
    vi.clearAllMocks();
  });

  it('init then isInitialized', async () => {
    const v = createVault();
    expect(await v.isInitialized()).toBe(false);
    const r = await v.init('twelve_char_x');
    expect(r.ok).toBe(true);
    expect(await v.isInitialized()).toBe(true);
    expect(v.isUnlocked()).toBe(true);
  });

  it('rejects passphrase shorter than 12', async () => {
    const v = createVault();
    const r = await v.init('short');
    expect(r.ok).toBe(false);
  });

  it('wrong passphrase on unlock', async () => {
    const v = createVault();
    await v.init('correct_pass12');
    v.lock();
    const r = await v.unlock('wrong___pass12');
    expect(r.ok).toBe(false);
    if (!r.ok) {
      expect(r.error).toBe('Incorrect passphrase');
    }
  });

  it('rejects init when vault already exists', async () => {
    const v = createVault();
    await v.init('first_pass_123');
    const r2 = await v.init('second_pass_12');
    expect(r2.ok).toBe(false);
  });

  it('addKey with stubbed validator stores ciphertext not plaintext', async () => {
    const v = createVault();
    await v.init('add_key_trip_12');
    const a = await v.addKey({
      provider: 'openai',
      label: 'L',
      key_value: 'sk-test-value-for-openai-1234567890',
    });
    expect(a.ok).toBe(true);
    if (a.ok) {
      const row = await getRecord(STORES.keys, a.key.id);
      expect(row.ciphertext_b64).toBeDefined();
      expect(String(row.ciphertext_b64).includes('sk-')).toBe(false);
    }
  });

  it('addKey on validation failure is not persisted', async () => {
    validateProviderKey.mockResolvedValueOnce({ ok: false, error: 'nope' });
    const v = createVault();
    await v.init('vfail_pass_123');
    const a = await v.addKey({ provider: 'openai', label: 'x', key_value: 'k' });
    expect(a.ok).toBe(false);
    const all = await getAllFromStore(STORES.keys);
    expect(all.length).toBe(0);
  });

  it('listKeys returns masked data without ciphertext', async () => {
    const v = createVault();
    await v.init('list_m_test_12');
    await v.addKey({ provider: 'openai', label: 'L', key_value: 'sk-abcdefghijklmnop' });
    const L = await v.listKeys();
    expect(L.length).toBe(1);
    expect(L[0].masked_preview).toBeDefined();
    expect(L[0].ciphertext_b64).toBeUndefined();
  });

  it('lock clears unlock state and listKeys empty', async () => {
    const v = createVault();
    await v.init('lock_test__12');
    v.lock();
    expect(v.isUnlocked()).toBe(false);
    expect((await v.listKeys()).length).toBe(0);
  });

  it('destroy clears all stores and emits', async () => {
    const v = createVault();
    let destroyed = 0;
    v.on('vault:destroyed', () => {
      destroyed += 1;
    });
    await v.init('destroy_test_12');
    await v.destroy();
    const meta = await getRecord(STORES.meta, 'vault');
    expect(meta).toBeNull();
    expect(destroyed).toBe(1);
  });

  it('unlock rejects tampered verification blob', async () => {
    const v = createVault();
    await v.init('tamper_tst_12');
    v.lock();
    const row = await getRecord(STORES.meta, 'vault');
    const ct = base64ToBytes(row.verify_ciphertext_b64);
    ct[0] ^= 0xff;
    await putRecord(STORES.meta, {
      ...row,
      verify_ciphertext_b64: bytesToBase64(ct),
    });
    const r = await v.unlock('tamper_tst_12');
    expect(r.ok).toBe(false);
  });

  it('unlocked/locked events', async () => {
    const v = createVault();
    let n = 0;
    v.on('vault:unlocked', () => {
      n += 1;
    });
    v.on('vault:locked', () => {
      n += 10;
    });
    await v.init('events_test_12');
    v.lock();
    expect(n).toBe(11);
  });
});
