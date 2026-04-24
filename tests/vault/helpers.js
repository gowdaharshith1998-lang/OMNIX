import { __test_resetDbConnection, closeVaultDb } from '../../src/web/vault/storage.js';
import { __test_resetListenerMap, createVault } from '../../src/web/vault/vault.js';
import { clearSessionStorageEntries } from '../../src/web/vault/session.js';

/**
 * Wipe IDB and vault singleton in-memory state between tests.
 * @returns {Promise<void>}
 */
export async function resetAllVault() {
  clearSessionStorageEntries();
  __test_resetListenerMap();
  const v = createVault();
  try {
    await v.destroy();
  } catch {
    // ignore
  }
  v.lock();
  await closeVaultDb();
  __test_resetDbConnection();
  await new Promise((r) => {
    const q = indexedDB.deleteDatabase('omnix_vault');
    q.onsuccess = q.onerror = () => r();
  });
  __test_resetDbConnection();
}
