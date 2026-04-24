import { describe, it, expect, beforeEach } from 'vitest';
import { resetAllVault } from './helpers.js';
import {
  saveSessionResumption,
  tryResumeFromSession,
  clearSessionStorageEntries,
} from '../../src/web/vault/session.js';
import {
  deriveVaultKeyFromPassphrase,
  randomSalt,
  constantTimeEqual,
  exportVaultKeyRaw,
} from '../../src/web/vault/crypto.js';

describe('session resumption', () => {
  beforeEach(async () => {
    await resetAllVault();
  });

  it('wrap/unwrap roundtrip', async () => {
    const k = await deriveVaultKeyFromPassphrase('wrap_unwrap_12c', randomSalt());
    await saveSessionResumption(k, 8);
    const out = await tryResumeFromSession();
    expect(out).not.toBeNull();
    const ra = await exportVaultKeyRaw(k);
    const rb = await exportVaultKeyRaw(/** @type {CryptoKey} */ (out));
    expect(constantTimeEqual(ra, rb)).toBe(true);
  });

  it('expired bundle is rejected', async () => {
    const k = await deriveVaultKeyFromPassphrase('expiry_tst_12c', randomSalt());
    await saveSessionResumption(k, 8);
    const raw = sessionStorage.getItem('omnix_vault_session_bundle');
    expect(raw).toBeTruthy();
    const o = JSON.parse(/** @type {string} */ (raw));
    o.e = Date.now() - 1;
    sessionStorage.setItem('omnix_vault_session_bundle', JSON.stringify(o));
    const out = await tryResumeFromSession();
    expect(out).toBeNull();
  });

  it('tampered ciphertext fails closed', async () => {
    const k = await deriveVaultKeyFromPassphrase('tamper_tst_12c', randomSalt());
    await saveSessionResumption(k, 8);
    const raw = sessionStorage.getItem('omnix_vault_session_bundle');
    const o = JSON.parse(/** @type {string} */ (raw));
    const { base64ToBytes, bytesToBase64 } = await import('../../src/web/vault/crypto.js');
    const c = base64ToBytes(o.c);
    c[0] ^= 1;
    o.c = bytesToBase64(c);
    sessionStorage.setItem('omnix_vault_session_bundle', JSON.stringify(o));
    const out = await tryResumeFromSession();
    expect(out).toBeNull();
  });

  it('clearSessionStorageEntries removes keys', async () => {
    const k = await deriveVaultKeyFromPassphrase('clear_test_12c', randomSalt());
    await saveSessionResumption(k, 8);
    clearSessionStorageEntries();
    expect(sessionStorage.getItem('omnix_vault_session_bundle')).toBeNull();
  });
});
