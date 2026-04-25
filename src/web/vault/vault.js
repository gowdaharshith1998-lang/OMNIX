/**
 * OMNIX encrypted API key vault: init, keys, routing, session policy.
 * Lost passphrase = lost vault; no recovery (C3). Keys never sent to OMNIX backends.
 * Compliance: P2, P15, P18, P20, P21, P22, P23, P24
 */
// Compliance: P22, P25

import {
  randomSalt,
  deriveVaultKeyFromPassphrase,
  encryptAesGcm,
  decryptAesGcm,
  constantTimeEqual,
  utf8Encode,
  utf8Decode,
  bytesToBase64,
  base64ToBytes,
  PBKDF2_ITERATIONS,
} from './crypto.js';
import { getRecord, putRecord, deleteRecord, getAllFromStore, clearAllVaultStores, STORES } from './storage.js';
import { validateProviderKey } from './validators.js';
import { saveSessionResumption, tryResumeFromSession, clearSessionStorageEntries } from './session.js';

const VAULT_ROW_ID = 'vault';
const VAULT_VERSION = 1;
/** @type {string} Decrypted to verify unlock; not persisted as plaintext (P24) */
const VAULT_VERIFICATION_PLAINTEXT = 'omnix_vault_v1';

const MIN_PASSPHRASE_LEN = 12;

/** @type {Map<string, Set<Function>>} */
const _listeners = new Map();

let _masterKey = null;

/**
 * @param {string} s
 * @param {import('./validators.js').VaultProvider} provider
 * @returns {string}
 */
function makeMaskedPreview(s, provider) {
  const t = String(s);
  if (t.length < 4) {
    return '…';
  }
  if (provider === 'ollama' && (t.startsWith('http://') || t.startsWith('https://'))) {
    const tail = t.slice(-6);
    return `…${tail.length ? tail : '…'}`;
  }
  if (provider === 'custom_openai') {
    if (t.length <= 8) {
      return `${t.slice(0, 1)}…${t.slice(-1)}`;
    }
    return `${t.slice(0, 4)}…${t.slice(-4)}`;
  }
  if (t.length <= 8) {
    return `${t.slice(0, 1)}…${t.slice(-1)}`;
  }
  return `${t.slice(0, 4)}…${t.slice(-4)}`;
}

/**
 * @param {string} event
 * @param {() => void} cb
 * @returns {void}
 */
function on(event, cb) {
  if (!_listeners.has(event)) {
    _listeners.set(event, new Set());
  }
  _listeners.get(event).add(cb);
}

/**
 * @param {string} event
 * @param {() => void} cb
 * @returns {void}
 */
function off(event, cb) {
  const s = _listeners.get(event);
  if (s) s.delete(cb);
}

/**
 * @param {string} event
 * @returns {void}
 */
function emit(event) {
  const s = _listeners.get(event);
  if (s) {
    for (const c of s) {
      c();
    }
  }
}

/**
 * @param {string} p
 * @returns {boolean}
 */
function isPassphraseAllowed(p) {
  return typeof p === 'string' && p.length >= MIN_PASSPHRASE_LEN;
}

/**
 * @returns {Promise<boolean>}
 */
async function isInitialized() {
  const row = await getRecord(STORES.meta, VAULT_ROW_ID);
  return row != null;
}

/**
 * @returns {boolean}
 */
function isUnlocked() {
  return _masterKey != null;
}

/**
 * @returns {void}
 */
function lock() {
  _masterKey = null;
  clearSessionStorageEntries();
  emit('vault:locked');
}

/**
 * @param {string} passphrase
 * @returns {Promise<{ok:true}|{ok:false,error:string}>}
 */
async function init(passphrase) {
  if (await isInitialized()) {
    return { ok: false, error: 'Vault already exists' };
  }
  if (!isPassphraseAllowed(passphrase)) {
    return { ok: false, error: 'Passphrase must be at least 12 characters' };
  }
  const salt = randomSalt();
  const key = await deriveVaultKeyFromPassphrase(passphrase, salt);
  const { ciphertext, iv } = await encryptAesGcm(key, utf8Encode(VAULT_VERIFICATION_PLAINTEXT));
  const row = {
    id: VAULT_ROW_ID,
    salt_b64: bytesToBase64(salt),
    iterations: PBKDF2_ITERATIONS,
    kdf_algo: 'PBKDF2-HMAC-SHA256',
    created_at: new Date().toISOString(),
    vault_version: VAULT_VERSION,
    verify_ciphertext_b64: bytesToBase64(ciphertext),
    verify_iv_b64: bytesToBase64(iv),
  };
  await putRecord(STORES.meta, row);
  _masterKey = key;
  emit('vault:unlocked');
  return { ok: true };
}

/**
 * @param {string} passphrase
 * @param {number} [rememberHours]
 * @returns {Promise<{ok:true}|{ok:false,error:string}>}
 */
async function unlock(passphrase, rememberHours = 0) {
  if (!isPassphraseAllowed(passphrase)) {
    return { ok: false, error: 'Incorrect passphrase' };
  }
  const row = await getRecord(STORES.meta, VAULT_ROW_ID);
  if (!row || !row.salt_b64 || !row.verify_ciphertext_b64 || !row.verify_iv_b64) {
    return { ok: false, error: 'Incorrect passphrase' };
  }
  const salt = base64ToBytes(row.salt_b64);
  const key = await deriveVaultKeyFromPassphrase(passphrase, salt);
  let okVerify = false;
  try {
    const ct = base64ToBytes(row.verify_ciphertext_b64);
    const iv = base64ToBytes(row.verify_iv_b64);
    const plain = await decryptAesGcm(key, ct, iv);
    okVerify = constantTimeEqual(plain, utf8Encode(VAULT_VERIFICATION_PLAINTEXT));
  } catch {
    okVerify = false;
  }
  if (!okVerify) {
    return { ok: false, error: 'Incorrect passphrase' };
  }
  _masterKey = key;
  if (rememberHours > 0) {
    await saveSessionResumption(key, rememberHours);
  }
  emit('vault:unlocked');
  return { ok: true };
}

/**
 * @returns {Promise<{ok:boolean}>}
 */
async function tryResumeFromSavedSession() {
  if (_masterKey) return { ok: true };
  const k = await tryResumeFromSession();
  if (!k) return { ok: false };
  _masterKey = k;
  emit('vault:unlocked');
  return { ok: true };
}

/**
 * @param {unknown} r
 * @returns {r is { id: string, provider: string, label: string, ciphertext_b64: string, iv_b64: string, created_at: string, last_validated_at: string, masked_preview: string }}
 */
function isKeyRec(r) {
  return (
    r != null &&
    typeof (/** @type {any} */ (r).id) === 'string' &&
    typeof (/** @type {any} */ (r).ciphertext_b64) === 'string'
  );
}

/**
 * @param {{ provider: import('./validators.js').VaultProvider, label: string, key_value: string, base_url?: string, skip_validation?: boolean }} p
 * @returns {Promise<{ok:true,key:object}|{ok:false,error:string}>}
 */
async function addKey(p) {
  if (!_masterKey) {
    return { ok: false, error: 'Vault locked' };
  }
  const { provider, label, key_value, base_url, skip_validation } = p;
  if (!provider || !label) {
    return { ok: false, error: 'Missing provider or label' };
  }
  const pr = String(provider);
  const bUrl = base_url != null && String(base_url).trim() ? String(base_url).trim() : undefined;
  if (pr === 'custom_openai' && !bUrl) {
    return { ok: false, error: 'Base URL required' };
  }
  if (pr === 'custom_openai' && !String(key_value).trim()) {
    return { ok: false, error: 'Key required' };
  }
  if (pr !== 'ollama' && pr !== 'custom_openai' && !String(key_value).trim()) {
    return { ok: false, error: 'Key required' };
  }
  const opts = bUrl ? { base_url: bUrl } : undefined;
  if (!skip_validation) {
    const v = await validateProviderKey(/** @type {any} */ (pr), String(key_value), opts);
    if (!v.ok) {
      return { ok: false, error: v.error };
    }
  }
  const id = crypto.randomUUID();
  const pt = new TextEncoder().encode(String(key_value));
  const { ciphertext, iv } = await encryptAesGcm(_masterKey, pt);
  pt.fill(0);
  const rec = {
    id,
    provider: pr,
    label: String(label).slice(0, 200),
    ciphertext_b64: bytesToBase64(ciphertext),
    iv_b64: bytesToBase64(iv),
    created_at: new Date().toISOString(),
    last_validated_at: new Date().toISOString(),
    masked_preview: makeMaskedPreview(String(key_value), pr),
    ...(bUrl && pr === 'custom_openai' ? { base_url: bUrl } : {}),
  };
  await putRecord(STORES.keys, rec);
  const { ciphertext_b64: _c, iv_b64: _i, ...pub } = rec;
  return { ok: true, key: pub };
}

/**
 * @returns {Promise<object[]>}
 */
async function listKeys() {
  if (!_masterKey) {
    return [];
  }
  const all = await getAllFromStore(STORES.keys);
  return all.map((r) => {
    if (!isKeyRec(r)) return r;
    const { ciphertext_b64, iv_b64, ...rest } = r;
    return rest;
  });
}

/**
 * @param {string} id
 * @returns {Promise<{ok:true,validated_at:string}|{ok:false,error:string}>}
 */
async function testKey(id) {
  if (!_masterKey) {
    return { ok: false, error: 'Vault locked' };
  }
  const r = await getRecord(STORES.keys, id);
  if (!isKeyRec(r)) {
    return { ok: false, error: 'Key not found' };
  }
  const ct = base64ToBytes(r.ciphertext_b64);
  const iv = base64ToBytes(r.iv_b64);
  let plain;
  try {
    const raw = await decryptAesGcm(_masterKey, ct, iv);
    plain = utf8Decode(raw);
  } catch {
    return { ok: false, error: 'Key decrypt failed' };
  }
  const rawB = (/** @type {any} */ (r).base_url);
  const bUrl = rawB != null && String(rawB).trim() ? String(rawB).trim() : undefined;
  const opts = bUrl ? { base_url: bUrl } : undefined;
  const v = await validateProviderKey(/** @type {any} */ (r).provider, plain, opts);
  if (!v.ok) {
    return { ok: false, error: v.error };
  }
  const at = new Date().toISOString();
  const upd = { ...r, last_validated_at: at };
  await putRecord(STORES.keys, upd);
  return { ok: true, validated_at: at };
}

/**
 * @param {string} id
 * @returns {Promise<{ok:true}|{ok:false,error:string}>}
 */
async function deleteKey(id) {
  if (!_masterKey) {
    return { ok: false, error: 'Vault locked' };
  }
  await deleteRecord(STORES.keys, id);
  return { ok: true };
}

/**
 * @param {string} agentId
 * @param {string} keyId
 * @returns {Promise<{ok:true}|{ok:false,error:string}>}
 */
async function assignAgent(agentId, keyId) {
  if (!_masterKey) {
    return { ok: false, error: 'Vault locked' };
  }
  const k = await getRecord(STORES.keys, keyId);
  if (!isKeyRec(k)) {
    return { ok: false, error: 'Key not found' };
  }
  const pr = String((/** @type {any} */ (k).provider) || '');
  await putRecord(STORES.routing, {
    agent_id: agentId,
    key_id: keyId,
    provider: pr,
    assigned_at: new Date().toISOString(),
  });
  return { ok: true };
}

/**
 * @param {string} agentId
 * @returns {Promise<{key_id:string,provider:string}|null>}
 */
async function getRoute(agentId) {
  const r = await getRecord(STORES.routing, agentId);
  if (!r || !r.key_id) return null;
  return { key_id: r.key_id, provider: String(r.provider || '') };
}

/**
 * @param {string} agentId
 * @returns {Promise<{provider:string,plaintext_key:string,base_url?:string}|null>}
 */
async function getProviderKeyForAgent(agentId) {
  if (!_masterKey) return null;
  const r = await getRecord(STORES.routing, agentId);
  if (!r || !r.key_id) return null;
  const key = await getRecord(STORES.keys, r.key_id);
  if (!isKeyRec(key)) return null;
  const ct = base64ToBytes(key.ciphertext_b64);
  const ivB = base64ToBytes(key.iv_b64);
  let raw;
  try {
    raw = await decryptAesGcm(_masterKey, ct, ivB);
  } catch {
    return null;
  }
  const plaintext_key = utf8Decode(raw);
  const rawB = (/** @type {any} */ (key).base_url);
  const base_url =
    rawB != null && String(rawB).trim() && String(/** @type {any} */ (key).provider) === 'custom_openai'
      ? String(rawB).trim()
      : undefined;
  if (base_url) {
    return { provider: String(r.provider), plaintext_key, base_url };
  }
  return { provider: String(r.provider), plaintext_key };
}

/**
 * @returns {Promise<{ok:true}|{ok:false,error:string}>}
 */
async function destroy() {
  _masterKey = null;
  clearSessionStorageEntries();
  await clearAllVaultStores();
  emit('vault:destroyed');
  _listeners.clear();
  return { ok: true };
}

let _apiSingleton = null;

/**
 * OMNIX vault API (process-wide singleton: shared key material and listeners).
 * @returns {{ isInitialized: () => Promise<boolean>, init: Function, unlock: Function, tryResumeFromSavedSession: Function, isUnlocked: () => boolean, lock: Function, addKey: Function, listKeys: Function, testKey: Function, deleteKey: Function, assignAgent: Function, getRoute: Function, getProviderKeyForAgent: Function, destroy: Function, on: Function, off: Function }}
 */
export function createVault() {
  if (_apiSingleton) return _apiSingleton;
  _apiSingleton = {
    isInitialized,
    init,
    unlock,
    tryResumeFromSavedSession,
    isUnlocked,
    lock,
    addKey,
    listKeys,
    testKey,
    deleteKey,
    assignAgent,
    getRoute,
    getProviderKeyForAgent,
    destroy,
    on,
    off,
  };
  return _apiSingleton;
}

/**
 * @internal test harness only: clears in-memory key and event listeners; call destroy() to wipe IDB.
 * @returns {void}
 */
export function __test_resetListenerMap() {
  _masterKey = null;
  _listeners.clear();
}
