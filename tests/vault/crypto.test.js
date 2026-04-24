import { describe, it, expect } from 'vitest';
import {
  randomSalt,
  deriveVaultKeyFromPassphrase,
  encryptAesGcm,
  decryptAesGcm,
  constantTimeEqual,
  utf8Encode,
  utf8Decode,
  randomBytes,
  base64ToBytes,
  bytesToBase64,
  exportVaultKeyRaw,
} from '../../src/web/vault/crypto.js';

describe('crypto', () => {
  it('KDF: same salt and passphrase produce matching encrypt/decrypt', async () => {
    const salt = randomSalt();
    const p = 'test_password_12chars';
    const a = await deriveVaultKeyFromPassphrase(p, salt);
    const b = await deriveVaultKeyFromPassphrase(p, salt);
    const ra = await exportVaultKeyRaw(a);
    const rb = await exportVaultKeyRaw(b);
    expect(constantTimeEqual(ra, rb)).toBe(true);
  });

  it('encrypt/decrypt roundtrip', async () => {
    const salt = randomSalt();
    const k = await deriveVaultKeyFromPassphrase('roundtrip_12b_test', salt);
    const { ciphertext, iv } = await encryptAesGcm(k, utf8Encode('hello'));
    const out = await decryptAesGcm(k, ciphertext, iv);
    expect(utf8Decode(out)).toBe('hello');
  });

  it('AES-GCM rejects tampered ciphertext', async () => {
    const salt = randomSalt();
    const k = await deriveVaultKeyFromPassphrase('tamper_trip_12c', salt);
    const { ciphertext, iv } = await encryptAesGcm(k, utf8Encode('x'));
    const bad = new Uint8Array(ciphertext);
    bad[0] ^= 1;
    await expect(async () => {
      await decryptAesGcm(k, bad, iv);
    }).rejects.toThrow();
  });

  it('1000 encryptions use unique IVs', async () => {
    const salt = randomSalt();
    const k = await deriveVaultKeyFromPassphrase('iv_uniq_12ch_test', salt);
    const set = new Set();
    for (let i = 0; i < 1000; i++) {
      const { iv } = await encryptAesGcm(k, utf8Encode(`m${i}`));
      set.add(bytesToBase64(iv));
    }
    expect(set.size).toBe(1000);
  });

  it('constantTimeEqual: equal and not equal', () => {
    const a = new Uint8Array([1, 2, 3]);
    const b = new Uint8Array([1, 2, 3]);
    const c = new Uint8Array([1, 2, 4]);
    expect(constantTimeEqual(a, b)).toBe(true);
    expect(constantTimeEqual(a, c)).toBe(false);
    expect(constantTimeEqual(a, new Uint8Array(2))).toBe(false);
  });

  it('base64 roundtrip is stable', () => {
    const b = randomBytes(32);
    expect(base64ToBytes(bytesToBase64(b).trim())).toEqual(b);
  });
});
