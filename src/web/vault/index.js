/**
 * OMNIX vault entry: singleton + optional UI binding. Compliance: P11–P16, P19–P21, P25.
 * @module
 */
// Compliance: P19, P21 (no KDF short-circuits; unlock only with passphrase or valid session)

import { createVault } from './vault.js';
import { createVaultUI } from './ui.js';

/**
 * Default vault instance for `omnix` web UI and embedders.
 * @type {ReturnType<typeof createVault>}
 */
export const vault = createVault();

/**
 * Boot: optional 8h session resume; wire toolbar button.
 * @returns {Promise<void>}
 */
async function boot() {
  await vault.tryResumeFromSavedSession();
  const btn = document.getElementById('btn-vault');
  if (btn) {
    createVaultUI(vault, btn);
  }
}

if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      void boot();
    });
  } else {
    void boot();
  }
}
