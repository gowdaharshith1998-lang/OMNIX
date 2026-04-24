/**
 * Promise-based IndexedDB access for the OMNIX vault. No idb library.
 * Database: omnix_vault, version 1; stores as per spec.
 * Compliance: P15 (no secret logging in storage paths), P22
 */
// Compliance: P22, P15

const DB_NAME = 'omnix_vault';
const DB_VERSION = 1;

const STORES = {
  meta: 'omnix_vault_meta',
  keys: 'omnix_vault_keys',
  routing: 'omnix_vault_routing',
};

let _dbPromise = null;

/** @internal */
export function __test_resetDbConnection() {
  _dbPromise = null;
}

/**
 * Close the open DB handle so deleteDatabase / tests can proceed.
 * @returns {Promise<void>}
 */
export async function closeVaultDb() {
  if (!_dbPromise) return;
  try {
    const db = await _dbPromise;
    db.close();
  } catch {
    // ignore
  }
  _dbPromise = null;
}

/**
 * @returns {Promise<IDBDatabase>}
 */
export function openVaultDb() {
  if (_dbPromise) return _dbPromise;
  _dbPromise = new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onerror = () => {
      const err = req.error;
      if (err) {
        // eslint-disable-next-line no-console
        console.error('omnix_vault: IndexedDB open failed', err.name);
      }
      reject(err || new Error('IndexedDB open failed'));
    };
    req.onsuccess = () => resolve(req.result);
    req.onupgradeneeded = (e) => {
      const db = e.target.result;
      if (!db.objectStoreNames.contains(STORES.meta)) {
        db.createObjectStore(STORES.meta, { keyPath: 'id' });
      }
      if (!db.objectStoreNames.contains(STORES.keys)) {
        db.createObjectStore(STORES.keys, { keyPath: 'id' });
      }
      if (!db.objectStoreNames.contains(STORES.routing)) {
        db.createObjectStore(STORES.routing, { keyPath: 'agent_id' });
      }
    };
  });
  return _dbPromise;
}

/**
 * @param {string} storeName
 * @param {string} id
 * @returns {Promise<unknown|null>}
 */
export async function getRecord(storeName, id) {
  const db = await openVaultDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(storeName, 'readonly');
    const st = tx.objectStore(storeName);
    const r = st.get(id);
    r.onsuccess = () => resolve(r.result ?? null);
    r.onerror = () => {
      // eslint-disable-next-line no-console
      if (r.error) console.error('omnix_vault: get failed', r.error.name);
      reject(r.error);
    };
  });
}

/**
 * @param {string} storeName
 * @param {unknown} value
 * @returns {Promise<void>}
 */
export async function putRecord(storeName, value) {
  const db = await openVaultDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(storeName, 'readwrite');
    const st = tx.objectStore(storeName);
    const r = st.put(value);
    r.onsuccess = () => resolve();
    r.onerror = () => {
      if (r.error) {
        // eslint-disable-next-line no-console
        console.error('omnix_vault: put failed', r.error.name);
      }
      reject(r.error);
    };
  });
}

/**
 * @param {string} storeName
 * @param {string} id
 * @returns {Promise<void>}
 */
export async function deleteRecord(storeName, id) {
  const db = await openVaultDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(storeName, 'readwrite');
    const st = tx.objectStore(storeName);
    const r = st.delete(id);
    r.onsuccess = () => resolve();
    r.onerror = () => {
      if (r.error) {
        // eslint-disable-next-line no-console
        console.error('omnix_vault: delete failed', r.error.name);
      }
      reject(r.error);
    };
  });
}

/**
 * @param {string} storeName
 * @returns {Promise<unknown[]>}
 */
export async function getAllFromStore(storeName) {
  const db = await openVaultDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(storeName, 'readonly');
    const st = tx.objectStore(storeName);
    const r = st.getAll();
    r.onsuccess = () => resolve(r.result || []);
    r.onerror = () => {
      if (r.error) {
        // eslint-disable-next-line no-console
        console.error('omnix_vault: getAll failed', r.error.name);
      }
      reject(r.error);
    };
  });
}

/**
 * @param {string} storeName
 * @returns {Promise<void>}
 */
export async function clearStore(storeName) {
  const db = await openVaultDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(storeName, 'readwrite');
    const st = tx.objectStore(storeName);
    const r = st.clear();
    r.onsuccess = () => resolve();
    r.onerror = () => {
      if (r.error) {
        // eslint-disable-next-line no-console
        console.error('omnix_vault: clear failed', r.error.name);
      }
      reject(r.error);
    };
  });
}

/**
 * Wipes meta, keys, routing in one place (destroy vault).
 * @returns {Promise<void>}
 */
export async function clearAllVaultStores() {
  await clearStore(STORES.meta);
  await clearStore(STORES.keys);
  await clearStore(STORES.routing);
}

export { STORES, DB_NAME, DB_VERSION };
