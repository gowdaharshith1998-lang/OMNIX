/**
 * "Remember vault for N hours": wrap exported master key with a session-only AES key;
 * opaque token lives in sessionStorage until expiry. No derived key in plaintext in storage.
 * Compliance: P11, P12, P15, P17, P22
 */
// Compliance: P11, P12, P15

import {
  bytesToBase64,
  base64ToBytes,
  encryptAesGcm,
  decryptAesGcm,
  exportVaultKeyRaw,
  importAesGcmKeyFromRaw,
  randomBytes,
} from './crypto.js';

const PREFIX = 'omnix_vault_session_';
const BUNDLE_KEY = `${PREFIX}bundle`;

/**
 * @returns {void}
 */
export function clearSessionStorageEntries() {
  if (typeof sessionStorage === 'undefined') return;
  const toRemove = [];
  for (let i = 0; i < sessionStorage.length; i++) {
    const k = sessionStorage.key(i);
    if (k && k.startsWith(PREFIX)) {
      toRemove.push(k);
    }
  }
  for (const k of toRemove) {
    sessionStorage.removeItem(k);
  }
}

/**
 * @param {CryptoKey} vaultKey Must be extractable (master key)
 * @param {number} rememberHours 1–168 (cap 8 per spec title; API allows hours)
 * @returns {Promise<void>}
 */
export async function saveSessionResumption(vaultKey, rememberHours) {
  clearSessionStorageEntries();
  const h = Math.min(Math.max(rememberHours, 0), 24 * 7);
  if (h <= 0) return;
  const exp = Date.now() + h * 60 * 60 * 1000;
  const token = randomBytes(32);
  const sessionKey = await importAesGcmKeyFromRaw(token, false);
  const raw = await exportVaultKeyRaw(vaultKey);
  let wrapped;
  try {
    const { ciphertext, iv } = await encryptAesGcm(sessionKey, raw);
    wrapped = {
      t: bytesToBase64(token),
      c: bytesToBase64(ciphertext),
      i: bytesToBase64(iv),
      e: exp,
    };
  } finally {
    raw.fill(0);
    token.fill(0);
  }
  sessionStorage.setItem(BUNDLE_KEY, JSON.stringify(wrapped));
}

/**
 * @returns {Promise<CryptoKey|null>} Restored master key, or null if none/expired/tamper
 */
export async function tryResumeFromSession() {
  if (typeof sessionStorage === 'undefined') return null;
  const j = sessionStorage.getItem(BUNDLE_KEY);
  if (!j) return null;
  let o;
  try {
    o = JSON.parse(j);
  } catch {
    clearSessionStorageEntries();
    return null;
  }
  if (typeof o.e !== 'number' || !o.t || !o.c || !o.i) {
    clearSessionStorageEntries();
    return null;
  }
  if (Date.now() > o.e) {
    clearSessionStorageEntries();
    return null;
  }
  let tokenU8;
  let ctU8;
  let ivU8;
  let raw;
  try {
    tokenU8 = base64ToBytes(o.t);
    if (tokenU8.length !== 32) {
      clearSessionStorageEntries();
      return null;
    }
    ctU8 = base64ToBytes(o.c);
    ivU8 = base64ToBytes(o.i);
    const sessionKey = await importAesGcmKeyFromRaw(tokenU8, false);
    tokenU8.fill(0);
    raw = await decryptAesGcm(sessionKey, ctU8, ivU8);
    const master = await importAesGcmKeyFromRaw(raw, true);
    raw.fill(0);
    return master;
  } catch {
    clearSessionStorageEntries();
    return null;
  }
}

/**
 * @returns {boolean} True if a non-expired bundle exists
 */
export function hasSessionResumption() {
  if (typeof sessionStorage === 'undefined') return false;
  const j = sessionStorage.getItem(BUNDLE_KEY);
  if (!j) return false;
  try {
    const o = JSON.parse(j);
    if (typeof o.e !== 'number' || Date.now() > o.e) {
      return false;
    }
    return true;
  } catch {
    return false;
  }
}

export { PREFIX };
