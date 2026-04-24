import { describe, it, expect, beforeEach } from 'vitest';
import {
  getRecord,
  putRecord,
  deleteRecord,
  getAllFromStore,
  clearAllVaultStores,
  STORES,
  __test_resetDbConnection,
  closeVaultDb,
} from '../../src/web/vault/storage.js';

async function wipe() {
  await closeVaultDb();
  __test_resetDbConnection();
  await new Promise((r) => {
    const q = indexedDB.deleteDatabase('omnix_vault');
    q.onsuccess = q.onerror = () => r();
  });
  __test_resetDbConnection();
}

describe('storage', () => {
  beforeEach(async () => {
    await wipe();
  });

  it('put/get roundtrip in meta', async () => {
    const row = { id: 'vault', salt_b64: 'c2FsdA' };
    await putRecord(STORES.meta, row);
    const g = await getRecord(STORES.meta, 'vault');
    expect(g).toEqual(row);
  });

  it('delete record', async () => {
    await putRecord(STORES.keys, { id: 'a', v: 1 });
    await deleteRecord(STORES.keys, 'a');
    const g = await getRecord(STORES.keys, 'a');
    expect(g).toBeNull();
  });

  it('getAllFromStore', async () => {
    await putRecord(STORES.keys, { id: 'k1', x: 1 });
    await putRecord(STORES.keys, { id: 'k2', x: 2 });
    const all = await getAllFromStore(STORES.keys);
    expect(all.length).toBe(2);
  });

  it('concurrent put operations complete', async () => {
    await Promise.all([
      putRecord(STORES.keys, { id: 'a', n: 1 }),
      putRecord(STORES.keys, { id: 'b', n: 2 }),
    ]);
    const n = (await getAllFromStore(STORES.keys)).length;
    expect(n).toBe(2);
  });

  it('clearAllVaultStores empties all', async () => {
    await putRecord(STORES.meta, { id: 'vault', x: 1 });
    await putRecord(STORES.keys, { id: 'k', x: 1 });
    await putRecord(STORES.routing, { agent_id: 'ag', x: 1 });
    await clearAllVaultStores();
    const m = await getAllFromStore(STORES.meta);
    const k = await getAllFromStore(STORES.keys);
    const r = await getAllFromStore(STORES.routing);
    expect(m.length + k.length + r.length).toBe(0);
  });
});
