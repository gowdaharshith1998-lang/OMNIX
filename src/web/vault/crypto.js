/**
 * Web Crypto (AES-256-GCM, PBKDF2-HMAC-SHA256) helpers for the OMNIX vault.
 * No third-party crypto — window.crypto.subtle only.
 * Compliance: P11, P12, P13, P14, P15, P17, P20 (KDF only; passphrase length checked in vault.js)
 */
// Compliance: P11, P12, P13, P15

const PBKDF2_ITERATIONS = 600_000;
const SALT_BYTES = 16;
const IV_BYTES = 12;
const AES_BITS = 256;
const B64 = 'base64';

/**
 * NIST SP 800-132–aligned KDF: PBKDF2-HMAC-SHA256, 600,000 iterations, 16-byte salt.
 * @param {string} passphrase User passphrase (length enforced by caller)
 * @param {Uint8Array} salt 16 fresh random bytes
 * @returns {Promise<CryptoKey>} AES-256-GCM key; extractable for session wrap/unwrap only
 */
export async function deriveVaultKeyFromPassphrase(passphrase, salt) {
  if (!(salt instanceof Uint8Array) || salt.length !== SALT_BYTES) {
    throw new Error('Invalid salt for key derivation');
  }
  const enc = new TextEncoder();
  const passphraseBytes = enc.encode(passphrase);
  const baseKey = await crypto.subtle.importKey('raw', passphraseBytes, 'PBKDF2', false, ['deriveKey']);
  const k = await crypto.subtle.deriveKey(
    {
      name: 'PBKDF2',
      salt,
      iterations: PBKDF2_ITERATIONS,
      hash: 'SHA-256',
    },
    baseKey,
    { name: 'AES-GCM', length: AES_BITS },
    true,
    ['encrypt', 'decrypt'],
  );
  passphraseBytes.fill(0);
  return k;
}

export { PBKDF2_ITERATIONS, SALT_BYTES, IV_BYTES, AES_BITS };

/**
 * @returns {Uint8Array} 16 fresh random bytes (salt)
 */
export function randomSalt() {
  const s = new Uint8Array(SALT_BYTES);
  crypto.getRandomValues(s);
  return s;
}

/**
 * @param {number} n
 * @returns {Uint8Array}
 */
export function randomBytes(n) {
  const b = new Uint8Array(n);
  crypto.getRandomValues(b);
  return b;
}

/**
 * @param {ArrayBuffer|Uint8Array} buf
 * @returns {string}
 */
export function bytesToBase64(buf) {
  const u8 = buf instanceof Uint8Array ? buf : new Uint8Array(buf);
  let bin = '';
  for (let i = 0; i < u8.length; i++) {
    bin += String.fromCharCode(u8[i]);
  }
  return btoa(bin);
}

/**
 * @param {string} b64
 * @returns {Uint8Array}
 */
export function base64ToBytes(b64) {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) {
    out[i] = bin.charCodeAt(i);
  }
  return out;
}

/**
 * AES-256-GCM encrypt; 12-byte IV; tag appended by Web Crypto (P12, P13).
 * @param {CryptoKey} key
 * @param {Uint8Array|ArrayBuffer} plaintext
 * @returns {Promise<{ ciphertext: Uint8Array, iv: Uint8Array }>}
 */
export async function encryptAesGcm(key, plaintext) {
  const iv = randomBytes(IV_BYTES);
  const pt = plaintext instanceof Uint8Array ? plaintext : new Uint8Array(plaintext);
  const ct = new Uint8Array(
    await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, pt),
  );
  return { ciphertext: ct, iv };
}

/**
 * @param {CryptoKey} key
 * @param {Uint8Array} ciphertext Full ciphertext + auth tag
 * @param {Uint8Array} iv 12 bytes
 * @returns {Promise<Uint8Array>}
 */
export async function decryptAesGcm(key, ciphertext, iv) {
  if (iv.length !== IV_BYTES) {
    const err = new Error('Decryption failed');
    throw err;
  }
  return new Uint8Array(await crypto.subtle.decrypt({ name: 'AES-GCM', iv }, key, ciphertext));
}

/**
 * Constant-time equality for equal-length byte arrays. Do not use === for secret data (P5, P6).
 * @param {Uint8Array} a
 * @param {Uint8Array} b
 * @returns {boolean}
 */
export function constantTimeEqual(a, b) {
  if (a.length !== b.length) return false;
  let d = 0;
  for (let i = 0; i < a.length; i++) {
    d |= a[i] ^ b[i];
  }
  return d === 0;
}

/**
 * @param {string} s
 * @returns {Uint8Array}
 */
export function utf8Encode(s) {
  return new TextEncoder().encode(s);
}

/**
 * @param {Uint8Array} b
 * @returns {string}
 */
export function utf8Decode(b) {
  return new TextDecoder('utf-8', { fatal: true }).decode(b);
}

/**
 * @param {CryptoKey} vaultKey
 * @returns {Promise<Uint8Array>}
 */
export async function exportVaultKeyRaw(vaultKey) {
  return new Uint8Array(await crypto.subtle.exportKey('raw', vaultKey));
}

/**
 * @param {Uint8Array} raw 32 bytes
 * @param {boolean} extractable
 * @returns {Promise<CryptoKey>}
 */
export async function importAesGcmKeyFromRaw(raw, extractable) {
  if (raw.length !== 32) {
    throw new Error('Invalid key material');
  }
  return crypto.subtle.importKey('raw', raw, { name: 'AES-GCM', length: AES_BITS }, extractable, [
    'encrypt',
    'decrypt',
  ]);
}
