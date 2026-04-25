/**
 * API key auto-detection panel (server-side scan, localhost OMNIX only).
 * Compliance: P11, C6 — uses vault.addKey; does not import crypto.
 */

/**
 * @param {HTMLElement} bodyEl
 * @param {ReturnType<import('./vault.js').createVault>} vault
 * @param {object} ctx
 * @param {() => void | Promise<void>} ctx.requestRender
 * @param {(p: string) => string} ctx.defaultLabel
 * @param {(p: string) => void} [ctx.onImported] flash the provider card
 */
export function mountScanSection(bodyEl, vault, ctx) {
  const wrap = document.createElement('div');
  wrap.className = 'scan-sect';
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'btn-ghost';
  btn.appendChild(
    document.createTextNode("🔍 Scan for existing keys"),
  );
  const status = document.createElement('p');
  status.className = 'msg muted';
  const list = document.createElement('div');
  list.className = 'scan-list';
  wrap.appendChild(btn);
  wrap.appendChild(status);
  wrap.appendChild(list);
  bodyEl.insertBefore(wrap, bodyEl.firstChild);

  let scanBusy = false;

  function iconFor(/** @type {string} */ p) {
    const letters = /** @type {Record<string, string>} */({
      anthropic: 'A',
      openai: 'O',
      google: 'G',
      ollama: 'L',
      xai: 'X',
      groq: 'Q',
      openrouter: 'R',
      huggingface: 'H',
    });
    return letters[p] || p.slice(0, 1).toUpperCase() || '\u2022';
  }

  btn.addEventListener('click', () => {
    void (async () => {
      if (scanBusy) return;
      scanBusy = true;
      list.replaceChildren();
      status.textContent = '';
      status.appendChild(
        document.createTextNode('Scanning this machine (localhost server)\u2026'),
      );
      const spin = document.createElement('span');
      spin.className = 'spin';
      spin.appendChild(document.createTextNode('\u00a0'));
      status.appendChild(spin);
      btn.disabled = true;
      try {
        const r = await fetch('/api/vault/scan', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: '{}',
        });
        if (r.status === 403) {
          status.textContent = 'Scan is only available from localhost OMNIX.';
          return;
        }
        if (!r.ok) {
          let msg = "Couldn't run scan. Try again.";
          try {
            const je = await r.json();
            if (je && je.error) msg = "Couldn't run scan (reference: " + String(je.id || '') + ')';
          } catch {
            /* */
          }
          status.textContent = msg;
          return;
        }
        const j = await r.json();
        const dets = j.detections;
        if (!dets || dets.length === 0) {
          status.replaceChildren();
          status.appendChild(
            document.createTextNode(
              'No keys found. You can add them manually using the provider cards above.',
            ),
          );
          return;
        }
        status.replaceChildren();
        for (const d of dets) {
          const row = document.createElement('div');
          row.className = 'scan-row';
          const ic = document.createElement('span');
          ic.className = 'p-dot';
          ic.style.minWidth = '24px';
          ic.style.minHeight = '24px';
          ic.style.width = '24px';
          ic.style.height = '24px';
          ic.style.fontSize = '12px';
          ic.appendChild(
            document.createTextNode(
              String(iconFor(/** @type {string} */ (d.provider))),
            ),
          );
          const mid = document.createElement('div');
          mid.className = 'scan-mid';
          const pv = document.createElement('div');
          pv.appendChild(
            document.createTextNode(
              String(d.provider) + ' \u00b7 ' + String(d.masked_preview),
            ),
          );
          const src = document.createElement('div');
          src.className = 'msg muted';
          src.style.fontSize = '11px';
          src.appendChild(document.createTextNode(String(d.source)));
          mid.appendChild(pv);
          mid.appendChild(src);
          const im = document.createElement('button');
          im.type = 'button';
          im.className = 'btn-ghost';
          im.appendChild(document.createTextNode('Import'));
          im.addEventListener('click', () => {
            void (async () => {
              im.disabled = true;
              let errEl = null;
              try {
                const cr = await fetch('/api/vault/scan/consume', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ detection_id: d.detection_id }),
                });
                const cj = await cr.json();
                if (!cr.ok || !cj.ok) {
                  im.disabled = false;
                  errEl = document.createElement('p');
                  errEl.className = 'msg err';
                  errEl.appendChild(
                    document.createTextNode(
                      String(cj.error || (cj.ok === false ? "Couldn't import" : 'Error')),
                    ),
                  );
                  row.appendChild(errEl);
                  return;
                }
                const addR = await vault.addKey({
                  provider: cj.provider,
                  label: ctx.defaultLabel(/** @type {any} */ (cj.provider)),
                  key_value: String(cj.key),
                });
                if (!addR.ok) {
                  im.disabled = false;
                  errEl = document.createElement('p');
                  errEl.className = 'msg err';
                  errEl.appendChild(
                    document.createTextNode(
                      String(/** @type {any} */ (addR).error || "Couldn't add key"),
                    ),
                  );
                  row.appendChild(errEl);
                  return;
                }
                row.replaceChildren();
                const ok = document.createElement('p');
                ok.className = 'msg ok';
                ok.appendChild(document.createTextNode('\u2713 Added'));
                row.appendChild(ok);
                if (typeof ctx.onImported === 'function') {
                  ctx.onImported(/** @type {string} */ (cj.provider));
                }
                void ctx.requestRender();
              } catch {
                im.disabled = false;
                errEl = document.createElement('p');
                errEl.className = 'msg err';
                errEl.appendChild(
                  document.createTextNode('Network error while importing'),
                );
                row.appendChild(errEl);
              }
            })();
          });
          row.appendChild(ic);
          row.appendChild(mid);
          row.appendChild(im);
          list.appendChild(row);
        }
      } catch {
        status.textContent = "Couldn't reach OMNIX scan (is the app running on localhost?)";
      } finally {
        scanBusy = false;
        btn.disabled = false;
      }
    })();
  });
}
