/**
 * Provider-first "Connect your AI" UI (Shadow DOM, vanilla). Presentation only.
 * Compliance: P11–P16, P18–P20, P25
 */
// Compliance: P22, P25

import { validateProviderKey } from './validators.js';
import { mountScanSection } from './ui-scan.js';

const UI_VER = '2c';

/** @type {const} */
const PROVIDERS = [
  {
    id: 'anthropic',
    displayName: 'Anthropic',
    valueProp: 'Claude models',
    letter: 'A',
    circle: '#f97316',
  },
  {
    id: 'openai',
    displayName: 'OpenAI',
    valueProp: 'GPT models',
    letter: 'O',
    circle: '#22c55e',
  },
  {
    id: 'google',
    displayName: 'Google',
    valueProp: 'Gemini models',
    letter: 'G',
    circle: '#3b82f6',
  },
  {
    id: 'ollama',
    displayName: 'Ollama (local)',
    valueProp: 'Run models on your machine',
    letter: 'L',
    circle: '#a855f7',
  },
];

/** @param {string} p */
function defaultLabel(p) {
  if (p === 'ollama') return 'Ollama';
  return PROVIDERS.find((x) => x.id === p)?.displayName ?? p;
}

/**
 * @param {unknown} err
 * @param {string} fallback
 * @returns {string}
 */
function userFacingError(err, fallback) {
  const s = err != null && typeof err === 'string' ? err : String(err ?? '');
  if (!s) return fallback;
  if (/\bVault locked\b/i.test(s)) {
    return 'Your keys are locked. Unlock to continue.';
  }
  return s;
}

/**
 * @param {ReturnType<import('./vault.js').createVault>} _vault
 * @param {HTMLElement | null} triggerButton
 * @returns {{ open: () => void, close: () => void, mount: () => void, unmount: () => void }}
 */
export function createVaultUI(_vault, triggerButton) {
  const vault = _vault;
  if (triggerButton) {
    triggerButton.textContent = '🔐 AI Keys';
  }

  let host = document.getElementById('omnix-vault-modal-host');
  if (!host) {
    host = document.createElement('div');
    host.id = 'omnix-vault-modal-host';
    document.body.appendChild(host);
  }
  // Stacking above Pixi/canvas: z-index on the light-DOM host; children use pointer-events: auto in CSS.
  host.style.cssText = 'position:fixed;inset:0;z-index:10000;pointer-events:none;';

  const shadow = host.attachShadow({ mode: 'open' });

  /** @type {'unlock' | 'grid' | 'changeLock' | 'reset1' | 'reset2'} */
  let view = 'grid';

  /** @param {typeof view} v */
  function setView(/** @type {typeof view} */ v) {
    view = v;
  }

  let expanded = /** @type {null | { id: string, mode: 'first' | 'add' | 'replace', replaceKeyId: string | null }} */ (
    null
  );
  let menuOpen = false;
  let menuProviderId = /** @type {string | null} */ (null);
  let successFlash = /** @type {null | { id: string, until: number }} */ (null);
  let keydownHandler = /** @type {((e: KeyboardEvent) => void) | null} */ (null);
  let confirmRemove = /** @type {null | { keyId: string, label: string }} */ (null);

  /** @type {Record<string, { phase: 'idle' | 'connecting' | 'ok' | 'err' }>} */
  const testUi = Object.create(null);

  /** @type {Record<string, boolean>} */
  const cardTestLine = Object.create(null);

  const vaultLns = /** @type {{ ev: string, fn: () => void }[]} */ ([]);

  function reattachListeners() {
    for (const { ev, fn } of vaultLns) {
      try {
        vault.off(ev, fn);
      } catch {
        /* */
      }
    }
    vaultLns.length = 0;
  }

  const onLocked = () => {
    if (openFlag) {
      void open();
    }
  };
  const onUnlocked = () => {
    if (openFlag) {
      void open();
    }
  };

  function reg(/** @type {string} */ ev, /** @type {() => void} */ fn) {
    vault.on(ev, fn);
    vaultLns.push({ ev, fn });
  }

  reattachListeners();
  reg('vault:locked', onLocked);
  reg('vault:unlocked', onUnlocked);

  const style = document.createElement('style');
  style.textContent = `
    :host {
      --omnix-bg: rgba(10, 14, 20, 0.98);
      --omnix-border: rgba(6, 182, 212, 0.45);
      --omnix-text: #e2e8f0;
      --omnix-muted: #94a3b8;
      --omnix-surface: rgba(2, 6, 23, 0.6);
      --omnix-input: rgba(15, 23, 42, 0.85);
      --omnix-err: #f87171;
      --omnix-ok: #4ade80;
      font-family: system-ui, -apple-system, sans-serif;
      color: var(--omnix-text);
      font-size: 15px;
    }
    * { box-sizing: border-box; }
    .backdrop {
      position: fixed; inset: 0; z-index: 0; display: none; align-items: center; justify-content: center; padding: 16px;
      background: rgba(2, 6, 21, 0.78);
      pointer-events: auto;
    }
    .backdrop.open { display: flex; }
    .panel { position: relative; width: 100%; max-width: 520px; max-height: 88vh; overflow: auto; background: var(--omnix-bg);
      border: 1px solid var(--omnix-border); border-radius: 12px; box-shadow: 0 20px 50px rgba(0,0,0,0.45);
    }
    .head { display: flex; align-items: center; justify-content: space-between; padding: 18px 20px 8px; border-bottom: 1px solid rgba(99, 102, 241, 0.2); position: relative; }
    h1 { margin: 0; font-size: 19px; font-weight: 600; color: #e0f2fe; }
    .head-actions { display: flex; gap: 4px; align-items: center; }
    .icon-btn, .icon-btn-ghost {
      background: transparent; border: none; color: var(--omnix-muted); cursor: pointer; font-size: 20px; line-height: 1; padding: 4px 8px; border-radius: 6px;
    }
    .icon-btn:hover, .icon-btn-ghost:hover { color: #e2e8f0; background: rgba(99, 102, 241, 0.12); }
    .body { padding: 16px 20px 20px; }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    @media (max-width: 480px) { .grid { grid-template-columns: 1fr; } }
    .p-card { border: 1px solid rgba(99, 102, 241, 0.22); border-radius: 10px; padding: 20px; background: var(--omnix-surface); position: relative; transition: border-color 0.12s ease, background 0.12s ease; }
    .p-card:hover { border-color: rgba(6, 182, 212, 0.55); background: rgba(15, 23, 42, 0.55); }
    .p-card.expanded { grid-column: 1 / -1; }
    .p-top { display: flex; gap: 12px; align-items: flex-start; }
    .p-dot { width: 40px; height: 40px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 18px; color: #0f172a; flex-shrink: 0; }
    .p-meta h2 { margin: 0; font-size: 16px; font-weight: 600; }
    .p-meta p { margin: 4px 0 0; color: var(--omnix-muted); font-size: 12px; line-height: 1.4; }
    .p-stripe { margin-top: 12px; }
    .linkish { background: transparent; border: none; color: #7dd3fc; cursor: pointer; font-size: 13px; font-weight: 500; padding: 0; text-decoration: underline; text-underline-offset: 2px; }
    .linkish:disabled { opacity: 0.5; cursor: not-allowed; }
    .menu-wrap { position: absolute; top: 10px; right: 8px; }
    .kebab { background: rgba(2,6,23,0.4); border: 1px solid rgba(99,102,241,0.2); color: var(--omnix-muted); border-radius: 4px; cursor: pointer; padding: 2px 8px; font-size: 14px; }
    .kebab:hover { color: #e2e8f0; border-color: rgba(6, 182, 212, 0.4); }
    .ctx-menu { position: absolute; right: 0; top: 100%; margin-top: 4px; min-width: 140px; background: rgba(15, 23, 42, 0.98); border: 1px solid rgba(6, 182, 212, 0.35); border-radius: 8px; padding: 4px; z-index: 5; }
    .ctx-menu button { display: block; width: 100%; text-align: left; background: transparent; border: none; color: #e2e8f0; padding: 8px 10px; font-size: 14px; cursor: pointer; border-radius: 4px; }
    .ctx-menu button:hover { background: rgba(99, 102, 241, 0.15); }
    .expand { margin-top: 14px; padding-top: 14px; border-top: 1px solid rgba(99, 102, 241, 0.2); }
    label { display: block; color: var(--omnix-muted); font-size: 12px; margin-bottom: 4px; }
    input { width: 100%; padding: 10px; border-radius: 6px; border: 1px solid rgba(148, 163, 184, 0.25); background: var(--omnix-input); color: #f8fafc; font-size: 14px; }
    .row { display: flex; gap: 8px; margin-top: 8px; align-items: center; }
    .row input { margin-top: 0; }
    .btn { display: inline-flex; align-items: center; justify-content: center; background: #4f46e5; color: #fff; border: none; border-radius: 6px; padding: 8px 16px; font-size: 14px; font-weight: 500; cursor: pointer; }
    .btn:disabled { opacity: 0.5; cursor: not-allowed; }
    .btn-ghost { background: transparent; border: 1px solid rgba(99, 102, 241, 0.4); color: #c7d2fe; }
    .msg { font-size: 13px; margin-top: 8px; }
    .msg.err { color: var(--omnix-err); }
    .msg.ok { color: var(--omnix-ok); }
    .msg.muted { color: var(--omnix-muted); font-size: 12px; line-height: 1.4; }
    .scan-sect { margin-bottom: 14px; padding-bottom: 12px; border-bottom: 1px solid rgba(99, 102, 241, 0.15); }
    .scan-list { display: flex; flex-direction: column; gap: 8px; margin-top: 8px; }
    .scan-row { display: flex; align-items: flex-start; gap: 10px; flex-wrap: wrap; }
    .scan-mid { flex: 1; min-width: 0; }
    .spin { color: #7dd3fc; }
    .gear-dd { position: absolute; right: 8px; top: 50px; min-width: 180px; z-index: 6; background: rgba(15, 23, 42, 0.98); border: 1px solid rgba(6, 182, 212, 0.35); border-radius: 8px; padding: 4px; }
    .gear-dd button { display: block; width: 100%; text-align: left; background: transparent; border: none; color: #e2e8f0; padding: 8px 10px; font-size: 14px; cursor: pointer; border-radius: 4px; }
    .gear-dd button:hover { background: rgba(99, 102, 241, 0.15); }
    .ov { position: fixed; inset: 0; background: rgba(2,6,21,0.5); z-index: 20; display: flex; align-items: center; justify-content: center; padding: 12px; }
    .ov-in { max-width: 400px; width: 100%; background: var(--omnix-bg); border: 1px solid var(--omnix-border); border-radius: 12px; padding: 20px; }
    .ov-in h2 { margin: 0 0 12px; font-size: 17px; }
    .ov-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 16px; flex-wrap: wrap; }
    .forgot { color: #7dd3fc; text-decoration: underline; cursor: pointer; font-size: 12px; margin-top: 8px; background: none; border: none; padding: 0; text-align: left; }
  `;
  shadow.appendChild(style);

  const backdrop = document.createElement('div');
  backdrop.className = 'backdrop';
  const panel = document.createElement('div');
  panel.className = 'panel';
  const mainLayer = document.createElement('div');
  const overlayLayer = document.createElement('div');
  panel.appendChild(mainLayer);
  panel.appendChild(overlayLayer);
  backdrop.appendChild(panel);
  shadow.appendChild(backdrop);

  let openFlag = false;

  function clearMenus() {
    menuOpen = false;
    menuProviderId = null;
  }

  /**
   * @param {import('./validators.js').VaultProvider} p
   * @param {string} key
   */
  async function verifyKey(p, key) {
    return validateProviderKey(/** @type {any} */ (p), key);
  }

  /**
   * @param {string} pid
   * @param {() => void} onDone
   */
  function runTestForProvider(/** @type {string} */ pid, onDone) {
    void (async () => {
      testUi[pid] = { phase: 'connecting' };
      cardTestLine[pid] = true;
      await render();
      const rows = await vault.listKeys();
      const k = rows.find((r) => r.provider === pid);
      if (!k) {
        testUi[pid] = { phase: 'err' };
        await render();
        onDone();
        return;
      }
      const t = await vault.testKey(String(k.id));
      if (t.ok) {
        testUi[pid] = { phase: 'ok' };
      } else {
        testUi[pid] = { phase: 'err' };
      }
      await render();
      onDone();
    })();
  }

  async function afterRenderFocus() {
    if (view === 'grid') {
      const first = mainLayer.querySelector('[data-pcard]');
      if (first) {
        (/** @type {HTMLElement} */ (first)).focus();
      }
    }
  }

  /**
   * @param {import('./validators.js').VaultProvider} provId
   * @param {typeof PROVIDERS[0]} def
   * @param {object[]} keyRows
   * @param {() => void} requestRender
   */
  function makeCard(/** @type {import('./validators.js').VaultProvider} */ provId, def, keyRows, requestRender) {
    const row = keyRows.find((r) => r.provider === provId);
    const hasKey = !!row;
    const isExp = expanded && expanded.id === provId;
    const wrap = document.createElement('div');
    wrap.className = 'p-card' + (isExp ? ' expanded' : '');
    wrap.tabIndex = 0;
    wrap.setAttribute('data-pcard', '1');

    const top = document.createElement('div');
    top.className = 'p-top';
    const dot = document.createElement('div');
    dot.className = 'p-dot';
    dot.style.background = def.circle;
    dot.appendChild(document.createTextNode(def.letter));
    const meta = document.createElement('div');
    meta.className = 'p-meta';
    const h2 = document.createElement('h2');
    h2.appendChild(document.createTextNode(def.displayName));
    const bl = document.createElement('p');
    bl.appendChild(document.createTextNode(def.valueProp));
    meta.appendChild(h2);
    meta.appendChild(bl);
    top.appendChild(dot);
    top.appendChild(meta);

    if (hasKey && row) {
      const menuW = document.createElement('div');
      menuW.className = 'menu-wrap';
      const kebab = document.createElement('button');
      kebab.type = 'button';
      kebab.className = 'kebab';
      kebab.appendChild(document.createTextNode('\u22ef'));
      kebab.setAttribute('aria-label', 'More');
      kebab.addEventListener('click', (e) => {
        e.stopPropagation();
        menuOpen = false;
        menuProviderId = menuProviderId === def.id ? null : def.id;
        void requestRender();
      });
      menuW.appendChild(kebab);
      if (menuProviderId === def.id) {
        const cm = document.createElement('div');
        cm.className = 'ctx-menu';
        const t1 = document.createElement('button');
        t1.type = 'button';
        t1.appendChild(document.createTextNode('Test'));
        t1.addEventListener('click', (e) => {
          e.stopPropagation();
          menuProviderId = null;
          runTestForProvider(/** @type {string} */ (def.id), () => {});
        });
        const t2 = document.createElement('button');
        t2.type = 'button';
        t2.appendChild(document.createTextNode('Replace key'));
        t2.addEventListener('click', (e) => {
          e.stopPropagation();
          menuProviderId = null;
          expanded = { id: def.id, mode: 'replace', replaceKeyId: String(row.id) };
          void requestRender();
        });
        const t3 = document.createElement('button');
        t3.type = 'button';
        t3.appendChild(document.createTextNode('Remove'));
        t3.addEventListener('click', (e) => {
          e.stopPropagation();
          menuProviderId = null;
          confirmRemove = { keyId: String(row.id), label: def.displayName };
          void requestRender();
        });
        cm.appendChild(t1);
        cm.appendChild(t2);
        cm.appendChild(t3);
        menuW.appendChild(cm);
      }
      top.appendChild(menuW);
    }

    wrap.appendChild(top);
    const stripe = document.createElement('div');
    stripe.className = 'p-stripe';
    if (!hasKey) {
      const add = document.createElement('button');
      add.type = 'button';
      add.className = 'linkish';
      add.appendChild(document.createTextNode('+ Connect'));
      add.addEventListener('click', (e) => {
        e.stopPropagation();
        void (async () => {
          const init = await vault.isInitialized();
          const unl = vault.isUnlocked();
          if (init && !unl) {
            setView('unlock');
            void requestRender();
            return;
          }
          if (!init) {
            expanded = { id: def.id, mode: 'first', replaceKeyId: null };
          } else {
            expanded = { id: def.id, mode: 'add', replaceKeyId: null };
          }
          void requestRender();
        })();
      });
      stripe.appendChild(add);
    } else {
      testUi[def.id] = testUi[def.id] || { phase: 'idle' };
      if (testUi[def.id].phase === 'connecting') {
        const sp = document.createElement('span');
        sp.className = 'spin';
        sp.appendChild(document.createTextNode('Testing\u2026'));
        stripe.appendChild(sp);
      } else if (testUi[def.id].phase !== 'idle' && cardTestLine[def.id]) {
        const st = document.createElement('p');
        st.className = 'msg' + (testUi[def.id].phase === 'ok' ? ' ok' : ' err');
        if (testUi[def.id].phase === 'ok') {
          st.appendChild(document.createTextNode('\u2713 Working'));
        } else {
          st.appendChild(document.createTextNode('\u2717 Key invalid \u00b7 '));
          const re = document.createElement('button');
          re.type = 'button';
          re.className = 'linkish';
          re.appendChild(document.createTextNode('Re-enter'));
          re.addEventListener('click', (ev) => {
            ev.stopPropagation();
            menuProviderId = null;
            if (row) {
              expanded = { id: def.id, mode: 'replace', replaceKeyId: String(row.id) };
            }
            testUi[def.id] = { phase: 'idle' };
            delete cardTestLine[def.id];
            void requestRender();
          });
          st.appendChild(re);
        }
        stripe.appendChild(st);
      } else {
        const statusBtn = document.createElement('button');
        statusBtn.type = 'button';
        statusBtn.className = 'linkish';
        statusBtn.appendChild(document.createTextNode('\u2713 Connected \u00b7 Test'));
        statusBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          runTestForProvider(/** @type {string} */ (def.id), () => {});
        });
        stripe.appendChild(statusBtn);
      }
    }
    wrap.appendChild(stripe);

    if (isExp && expanded) {
      const ex = document.createElement('div');
      ex.className = 'expand';
      const isFirst = expanded.mode === 'first';
      const apiL = document.createElement('label');
      apiL.appendChild(document.createTextNode('API key'));
      const keyIn = document.createElement('input');
      keyIn.type = 'password';
      keyIn.setAttribute('autocomplete', 'off');
      keyIn.setAttribute('spellcheck', 'false');
      keyIn.setAttribute('autocapitalize', 'none');
      keyIn.setAttribute('data-lpignore', 'true');
      keyIn.setAttribute('data-1p-ignore', 'true');
      const rowPaste = document.createElement('div');
      rowPaste.className = 'row';
      const pasteB = document.createElement('button');
      pasteB.type = 'button';
      pasteB.className = 'btn-ghost';
      pasteB.appendChild(document.createTextNode('Paste'));
      pasteB.addEventListener('click', async () => {
        try {
          const t = await navigator.clipboard.readText();
          keyIn.value = t;
        } catch {
          /* */
        }
      });
      rowPaste.appendChild(keyIn);
      rowPaste.appendChild(pasteB);
      ex.appendChild(apiL);
      ex.appendChild(rowPaste);
      let lockIn = null;
      if (isFirst) {
        const ll = document.createElement('label');
        ll.appendChild(document.createTextNode('Lock code (12+ characters)'));
        lockIn = document.createElement('input');
        lockIn.type = 'password';
        lockIn.setAttribute('autocomplete', 'new-password');
        lockIn.setAttribute('spellcheck', 'false');
        lockIn.setAttribute('autocapitalize', 'none');
        const lockH = document.createElement('p');
        lockH.className = 'msg muted';
        lockH.appendChild(
          document.createTextNode('Protects your keys on this device. No recovery \u2014 keep it somewhere safe.'),
        );
        ex.appendChild(ll);
        ex.appendChild(lockIn);
        ex.appendChild(lockH);
      }
      const cmsg = document.createElement('p');
      cmsg.className = 'msg err';
      cmsg.style.display = 'none';
      const crow = document.createElement('div');
      crow.className = 'row';
      const cbtn = document.createElement('button');
      cbtn.type = 'button';
      cbtn.className = 'btn';
      cbtn.appendChild(document.createTextNode('Connect'));
      const spin = document.createElement('span');
      spin.className = 'spin';
      spin.style.display = 'none';
      spin.appendChild(document.createTextNode('Testing connection\u2026'));
      crow.appendChild(cbtn);
      crow.appendChild(spin);
      ex.appendChild(cmsg);
      ex.appendChild(crow);

      cbtn.addEventListener('click', () => {
        void (async () => {
          cmsg.replaceChildren();
          cmsg.style.display = 'none';
          const raw = String(keyIn.value);
          const kval =
            def.id === 'ollama' && !raw.trim() ? 'http://127.0.0.1:11434' : raw.trim();
          if (isFirst) {
            if (!lockIn || String(lockIn.value).length < 12) {
              cmsg.appendChild(document.createTextNode('Enter a lock code of at least 12 characters.'));
              cmsg.style.display = 'block';
              return;
            }
            if (def.id !== 'ollama' && !kval) {
              cmsg.appendChild(document.createTextNode('Enter your API key, then try again.'));
              cmsg.style.display = 'block';
              return;
            }
          } else {
            if (def.id !== 'ollama' && !kval) {
              cmsg.appendChild(document.createTextNode('Enter your API key, then try again.'));
              cmsg.style.display = 'block';
              return;
            }
          }
          cbtn.disabled = true;
          spin.style.display = 'inline';
          const v = await verifyKey(
            /** @type {import('./validators.js').VaultProvider} */ (def.id),
            kval,
          );
          if (!v.ok) {
            cmsg.replaceChildren();
            cmsg.appendChild(
              document.createTextNode("Couldn't connect \u2014 check the key and try again"),
            );
            cmsg.style.display = 'block';
            cbtn.disabled = false;
            spin.style.display = 'none';
            return;
          }
          if (isFirst) {
            const i = await vault.init(String((/** @type {HTMLInputElement} */ (lockIn)).value));
            if (!i.ok) {
              cmsg.replaceChildren();
              cmsg.appendChild(
                document.createTextNode(
                  userFacingError(
                    (/** @type {any} */ (i).error),
                    "Couldn't finish setup. Try again.",
                  ),
                ),
              );
              cmsg.style.display = 'block';
              cbtn.disabled = false;
              spin.style.display = 'none';
              return;
            }
          } else {
            if (!vault.isUnlocked()) {
              cmsg.replaceChildren();
              cmsg.appendChild(document.createTextNode('Your keys are locked. Unlock to continue.'));
              cmsg.style.display = 'block';
              cbtn.disabled = false;
              spin.style.display = 'none';
              return;
            }
          }
          if (expanded.mode === 'replace' && expanded.replaceKeyId) {
            await vault.deleteKey(expanded.replaceKeyId);
          }
          const addR = await vault.addKey({
            provider: def.id,
            label: defaultLabel(def.id),
            key_value: kval,
          });
          if (!addR.ok) {
            cmsg.replaceChildren();
            cmsg.appendChild(
              document.createTextNode(
                userFacingError(
                  (/** @type {any} */ (addR).error),
                  "Couldn't connect \u2014 check the key and try again",
                ),
              ),
            );
            cmsg.style.display = 'block';
            cbtn.disabled = false;
            spin.style.display = 'none';
            return;
          }
          keyIn.value = '';
          if (lockIn) {
            (/** @type {HTMLInputElement} */ (lockIn)).value = '';
          }
          cbtn.disabled = false;
          spin.style.display = 'none';
          expanded = null;
          const pid = def.id;
          successFlash = { id: pid, until: Date.now() + 1500 };
          setTimeout(() => {
            successFlash = null;
            if (openFlag) {
              void requestRender();
            }
          }, 1500);
          void requestRender();
        })();
      });
      ex.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && cbtn) {
          e.preventDefault();
          cbtn.click();
        }
      });
      wrap.appendChild(ex);
      if (openFlag) {
        setTimeout(() => {
          keyIn.focus();
        }, 0);
      }
    }
    return wrap;
  }

  function makeClose() {
    const closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.className = 'icon-btn';
    closeBtn.setAttribute('aria-label', 'Close');
    closeBtn.appendChild(document.createTextNode('\u2715'));
    closeBtn.addEventListener('click', () => {
      doClose();
    });
    return closeBtn;
  }

  function makeGear(/** @type {() => Promise<void>} */ requestRender) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'icon-btn-ghost';
    b.setAttribute('aria-label', 'Menu');
    b.appendChild(document.createTextNode('\u2699'));
    b.addEventListener('click', (e) => {
      e.stopPropagation();
      menuOpen = !menuOpen;
      void requestRender();
    });
    return b;
  }

  function buildRemoveOverlay(/** @type {() => void} */ requestRender) {
    if (!confirmRemove) return;
    const ov = document.createElement('div');
    ov.className = 'ov';
    const inn = document.createElement('div');
    inn.className = 'ov-in';
    const h2a = document.createElement('h2');
    h2a.appendChild(document.createTextNode('Remove this connection?'));
    const p = document.createElement('p');
    p.className = 'msg muted';
    p.appendChild(
      document.createTextNode("You'll need to add the API key again to use " + confirmRemove.label + '.'),
    );
    const act = document.createElement('div');
    act.className = 'ov-actions';
    const ca = document.createElement('button');
    ca.type = 'button';
    ca.className = 'btn-ghost';
    ca.appendChild(document.createTextNode('Cancel'));
    const rm = document.createElement('button');
    rm.type = 'button';
    rm.className = 'btn';
    rm.appendChild(document.createTextNode('Remove'));
    const kid = confirmRemove.keyId;
    const provLabel = confirmRemove.label;
    ca.addEventListener('click', () => {
      confirmRemove = null;
      void requestRender();
    });
    rm.addEventListener('click', async () => {
      const id = kid;
      await vault.deleteKey(id);
      const delProv = PROVIDERS.find((d) => d.displayName === provLabel);
      if (delProv) {
        testUi[delProv.id] = { phase: 'idle' };
        delete cardTestLine[delProv.id];
      }
      confirmRemove = null;
      void requestRender();
    });
    act.appendChild(ca);
    act.appendChild(rm);
    inn.appendChild(h2a);
    inn.appendChild(p);
    inn.appendChild(act);
    ov.appendChild(inn);
    ov.addEventListener('click', (ev) => {
      if (ev.target === ov) {
        confirmRemove = null;
        void requestRender();
      }
    });
    overlayLayer.appendChild(ov);
  }

  /**
   * @returns {Promise<void>}
   */
  async function render() {
    if (successFlash && Date.now() >= successFlash.until) {
      successFlash = null;
    }
    mainLayer.replaceChildren();
    overlayLayer.replaceChildren();
    if (confirmRemove) {
      buildRemoveOverlay(() => render());
      return;
    }

    if (view === 'unlock') {
      const head = document.createElement('div');
      head.className = 'head';
      const h1 = document.createElement('h1');
      h1.appendChild(document.createTextNode('Unlock your keys'));
      const ra = document.createElement('div');
      ra.className = 'head-actions';
      ra.appendChild(makeClose());
      head.appendChild(h1);
      head.appendChild(ra);
      mainLayer.appendChild(head);
      const body = document.createElement('div');
      body.className = 'body';
      const lb = document.createElement('label');
      lb.appendChild(document.createTextNode('Lock code'));
      const inEl = document.createElement('input');
      inEl.type = 'password';
      inEl.setAttribute('autocomplete', 'off');
      inEl.setAttribute('spellcheck', 'false');
      inEl.setAttribute('autocapitalize', 'none');
      inEl.setAttribute('data-lpignore', 'true');
      inEl.setAttribute('data-1p-ignore', 'true');
      const rem = document.createElement('div');
      rem.className = 'row';
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      const cl = document.createElement('label');
      cl.appendChild(document.createTextNode('Remember for 8 hours on this device'));
      rem.appendChild(cb);
      rem.appendChild(cl);
      const unBtn = document.createElement('button');
      unBtn.type = 'button';
      unBtn.className = 'btn';
      unBtn.appendChild(document.createTextNode('Unlock'));
      const unMsg = document.createElement('p');
      unMsg.className = 'msg err';
      unMsg.style.display = 'none';
      unBtn.addEventListener('click', async () => {
        unMsg.replaceChildren();
        unMsg.style.display = 'none';
        const h = cb.checked ? 8 : 0;
        const r = await vault.unlock(inEl.value, h);
        if (!r.ok) {
          unMsg.appendChild(
            document.createTextNode(
              userFacingError(
                (/** @type {any} */ (r).error),
                "Couldn't unlock. Check your lock code.",
              ),
            ),
          );
          unMsg.style.display = 'block';
          return;
        }
        inEl.value = '';
        setView('grid');
        await render();
        void afterRenderFocus();
      });
      const forgWrap = document.createElement('div');
      const forg = document.createElement('button');
      forg.type = 'button';
      forg.className = 'forgot';
      forg.appendChild(document.createTextNode('Forgot? \u2192'));
      const forgH = document.createElement('p');
      forgH.className = 'msg muted';
      forgH.style.display = 'none';
      forgH.appendChild(
        document.createTextNode("There's no recovery. You'll need to re-add your keys. "),
      );
      const resL = document.createElement('button');
      resL.type = 'button';
      resL.className = 'linkish';
      resL.appendChild(document.createTextNode('Reset device'));
      resL.addEventListener('click', () => {
        setView('reset1');
        void render();
      });
      forgH.appendChild(resL);
      forg.addEventListener('click', () => {
        const vis = forgH.style.display;
        forgH.style.display = vis === 'none' || !vis ? 'block' : 'none';
      });
      body.appendChild(lb);
      body.appendChild(inEl);
      body.appendChild(rem);
      body.appendChild(unBtn);
      body.appendChild(unMsg);
      forgWrap.appendChild(forg);
      forgWrap.appendChild(forgH);
      body.appendChild(forgWrap);
      mainLayer.appendChild(body);
      if (openFlag) {
        inEl.focus();
      }
      return;
    }

    if (view === 'changeLock') {
      const ov = document.createElement('div');
      ov.className = 'ov';
      const inn = document.createElement('div');
      inn.className = 'ov-in';
      const h2 = document.createElement('h2');
      h2.appendChild(document.createTextNode('Change lock code'));
      const p = document.createElement('p');
      p.className = 'msg muted';
      p.appendChild(
        document.createTextNode(
          'This removes your saved connection keys on this device. You can connect again afterward.',
        ),
      );
      const l1 = document.createElement('label');
      l1.appendChild(document.createTextNode('Current lock code'));
      const oin = document.createElement('input');
      oin.type = 'password';
      oin.setAttribute('autocomplete', 'off');
      oin.setAttribute('spellcheck', 'false');
      oin.setAttribute('autocapitalize', 'none');
      oin.setAttribute('data-lpignore', 'true');
      oin.setAttribute('data-1p-ignore', 'true');
      const l2 = document.createElement('label');
      l2.appendChild(document.createTextNode('New lock code (12+ characters)'));
      const nin = document.createElement('input');
      nin.type = 'password';
      nin.setAttribute('autocomplete', 'new-password');
      nin.setAttribute('spellcheck', 'false');
      nin.setAttribute('autocapitalize', 'none');
      const err = document.createElement('p');
      err.className = 'msg err';
      err.style.display = 'none';
      const act = document.createElement('div');
      act.className = 'ov-actions';
      const cancel = document.createElement('button');
      cancel.type = 'button';
      cancel.className = 'btn-ghost';
      cancel.appendChild(document.createTextNode('Cancel'));
      const go = document.createElement('button');
      go.type = 'button';
      go.className = 'btn';
      go.appendChild(document.createTextNode('Update'));
      cancel.addEventListener('click', () => {
        setView('grid');
        void render();
      });
      go.addEventListener('click', async () => {
        err.replaceChildren();
        err.style.display = 'none';
        if (String(nin.value).length < 12) {
          err.appendChild(
            document.createTextNode('New lock code must be at least 12 characters.'),
          );
          err.style.display = 'block';
          return;
        }
        vault.lock();
        const u = await vault.unlock(oin.value, 0);
        if (!u.ok) {
          err.appendChild(
            document.createTextNode(
              userFacingError(
                (/** @type {any} */ (u).error),
                "Current lock code doesn't match.",
              ),
            ),
          );
          err.style.display = 'block';
          return;
        }
        await vault.destroy();
        reattachListeners();
        reg('vault:locked', onLocked);
        reg('vault:unlocked', onUnlocked);
        const i = await vault.init(nin.value);
        if (!i.ok) {
          err.appendChild(
            document.createTextNode(
              userFacingError(
                (/** @type {any} */ (i).error),
                "Couldn't set new lock code.",
              ),
            ),
          );
          err.style.display = 'block';
          return;
        }
        oin.value = '';
        nin.value = '';
        setView('grid');
        expanded = null;
        clearMenus();
        void render();
      });
      act.appendChild(cancel);
      act.appendChild(go);
      inn.appendChild(h2);
      inn.appendChild(p);
      inn.appendChild(l1);
      inn.appendChild(oin);
      inn.appendChild(l2);
      inn.appendChild(nin);
      inn.appendChild(err);
      inn.appendChild(act);
      ov.appendChild(inn);
      ov.addEventListener('click', (e) => {
        if (e.target === ov) {
          setView('grid');
          void render();
        }
      });
      overlayLayer.appendChild(ov);
      if (openFlag) {
        oin.focus();
      }
      return;
    }

    if (view === 'reset1' || view === 'reset2') {
      const ov = document.createElement('div');
      ov.className = 'ov';
      const inn = document.createElement('div');
      inn.className = 'ov-in';
      const h2x = document.createElement('h2');
      h2x.appendChild(document.createTextNode('Reset this device?'));
      const px = document.createElement('p');
      px.className = 'msg muted';
      px.appendChild(
        document.createTextNode('This removes your saved connection keys. There is no recovery.'),
      );
      const act = document.createElement('div');
      act.className = 'ov-actions';
      if (view === 'reset1') {
        const cancel = document.createElement('button');
        cancel.type = 'button';
        cancel.className = 'btn-ghost';
        cancel.appendChild(document.createTextNode('Cancel'));
        const cont = document.createElement('button');
        cont.type = 'button';
        cont.className = 'btn';
        cont.appendChild(document.createTextNode('Continue'));
        cancel.addEventListener('click', () => {
          setView('grid');
          void render();
        });
        cont.addEventListener('click', () => {
          setView('reset2');
          void render();
        });
        act.appendChild(cancel);
        act.appendChild(cont);
        inn.appendChild(h2x);
        inn.appendChild(px);
        inn.appendChild(act);
      } else {
        const warn = document.createElement('p');
        warn.className = 'msg err';
        warn.appendChild(
          document.createTextNode('This is permanent. Every saved key will be removed.'),
        );
        const delBtn = document.createElement('button');
        delBtn.type = 'button';
        delBtn.className = 'btn';
        delBtn.appendChild(document.createTextNode('Delete everything now'));
        const back = document.createElement('button');
        back.type = 'button';
        back.className = 'btn-ghost';
        back.appendChild(document.createTextNode('Back'));
        delBtn.addEventListener('click', async () => {
          await vault.destroy();
          reattachListeners();
          reg('vault:locked', onLocked);
          reg('vault:unlocked', onUnlocked);
          setView('grid');
          expanded = null;
          successFlash = null;
          for (const k of Object.keys(testUi)) {
            delete testUi[k];
          }
          for (const k2 of Object.keys(cardTestLine)) {
            delete cardTestLine[k2];
          }
          void render();
        });
        back.addEventListener('click', () => {
          setView('reset1');
          void render();
        });
        act.appendChild(back);
        act.appendChild(delBtn);
        inn.appendChild(h2x);
        inn.appendChild(px);
        inn.appendChild(warn);
        inn.appendChild(act);
      }
      ov.appendChild(inn);
      ov.addEventListener('click', (e) => {
        if (e.target === ov) {
          setView('grid');
          void render();
        }
      });
      overlayLayer.appendChild(ov);
      return;
    }

    if (view === 'grid') {
      const head = document.createElement('div');
      head.className = 'head';
      const h1 = document.createElement('h1');
      h1.appendChild(document.createTextNode('Connect your AI'));
      const ra = document.createElement('div');
      ra.className = 'head-actions';
      if (menuOpen) {
        const dd = document.createElement('div');
        dd.className = 'gear-dd';
        const b1 = document.createElement('button');
        b1.type = 'button';
        b1.appendChild(document.createTextNode('Lock'));
        b1.addEventListener('click', () => {
          clearMenus();
          vault.lock();
          void open();
        });
        const b2 = document.createElement('button');
        b2.type = 'button';
        b2.appendChild(document.createTextNode('Change lock code'));
        b2.addEventListener('click', () => {
          clearMenus();
          setView('changeLock');
          void render();
        });
        const b3 = document.createElement('button');
        b3.type = 'button';
        b3.appendChild(document.createTextNode('Reset everything'));
        b3.addEventListener('click', () => {
          clearMenus();
          setView('reset1');
          void render();
        });
        dd.appendChild(b1);
        dd.appendChild(b2);
        dd.appendChild(b3);
        head.appendChild(h1);
        ra.appendChild(makeGear(() => render()));
        ra.appendChild(makeClose());
        head.appendChild(ra);
        head.appendChild(dd);
      } else {
        head.appendChild(h1);
        ra.appendChild(makeGear(() => render()));
        ra.appendChild(makeClose());
        head.appendChild(ra);
      }
      mainLayer.appendChild(head);
      if (successFlash) {
        const t = successFlash;
        if (Date.now() < t.until) {
          const fl = document.createElement('p');
          fl.className = 'msg ok';
          const label = PROVIDERS.find((p) => p.id === t.id);
          const nm = label ? label.displayName : t.id;
          fl.appendChild(
            document.createTextNode('\u2713 ' + nm + ' connected'),
          );
          const body0 = document.createElement('div');
          body0.className = 'body';
          body0.style.paddingTop = '0';
          body0.appendChild(fl);
          mainLayer.appendChild(body0);
        } else {
          successFlash = null;
        }
      }
      const body = document.createElement('div');
      body.className = 'body';
      const initOk = await vault.isInitialized();
      const unlOk = vault.isUnlocked();
      if (initOk && unlOk) {
        mountScanSection(body, vault, {
          requestRender: () => {
            void render();
          },
          defaultLabel,
          onImported: (pid) => {
            successFlash = { id: String(pid), until: Date.now() + 1500 };
          },
        });
      }
      const g = document.createElement('div');
      g.className = 'grid';
      const keys = await vault.listKeys();
      for (const def of PROVIDERS) {
        g.appendChild(
          makeCard(
            /** @type {import('./validators.js').VaultProvider} */ (def.id),
            def,
            keys,
            () => render(),
          ),
        );
      }
      body.appendChild(g);
      mainLayer.appendChild(body);
      if (openFlag) {
        void afterRenderFocus();
      }
    }
  }

  function doClose() {
    backdrop.classList.remove('open');
    openFlag = false;
    clearMenus();
    if (keydownHandler) {
      document.removeEventListener('keydown', keydownHandler);
      keydownHandler = null;
    }
  }

  function bindGlobalKeys() {
    if (keydownHandler) {
      document.removeEventListener('keydown', keydownHandler);
    }
    keydownHandler = (e) => {
      if (e.key === 'Escape' && openFlag) {
        e.preventDefault();
        if (view === 'changeLock' || view === 'reset1' || view === 'reset2' || confirmRemove) {
          if (confirmRemove) {
            confirmRemove = null;
          } else {
            setView('grid');
          }
          void render();
        } else {
          doClose();
        }
      }
      if ((e.metaKey || e.ctrlKey) && (e.key === 'k' || e.key === 'K')) {
        e.preventDefault();
        void open();
      }
    };
    document.addEventListener('keydown', keydownHandler);
  }

  async function open() {
    openFlag = true;
    bindGlobalKeys();
    await vault.tryResumeFromSavedSession();
    const init = await vault.isInitialized();
    const unl = vault.isUnlocked();
    if (init && !unl) {
      setView('unlock');
    } else {
      setView('grid');
    }
    if (view === 'grid' && successFlash && Date.now() >= successFlash.until) {
      successFlash = null;
    }
    backdrop.classList.add('open');
    await render();
  }

  function close() {
    doClose();
  }

  function unmount() {
    close();
    reattachListeners();
    if (host && host.parentNode) {
      host.parentNode.removeChild(host);
    }
  }

  function mount() {
    if (host && !host.parentNode) {
      document.body.appendChild(host);
    }
  }

  shadow.appendChild(document.createComment(` ui ${UI_VER} `));

  if (triggerButton) {
    triggerButton.addEventListener('click', () => {
      void open();
    });
  }

  return { open, close, mount, unmount };
}
