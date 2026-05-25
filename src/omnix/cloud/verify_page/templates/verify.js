// OMNIX client-side verifier loader.
//
// Prefers the in-bundle WASM verifier. When absent (current scaffold), falls
// back to the server endpoint. Either way the public-key check is identical;
// the WASM path just gives you independent verifiability in the browser.
//
// To install the WASM verifier, compile the pure-Python module at
// src/omnix/receipts/verify.py to Pyodide and host it under /verify/wasm/.

(function() {
  async function verifyViaServer(payload) {
    const resp = await fetch('/verify/api/verify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (!resp.ok) throw new Error('verify endpoint ' + resp.status);
    return await resp.json();
  }

  // Stub WASM dispatch table — keeps the API stable so the HTML page can
  // call window.__omnix_verify(...) regardless of whether WASM is loaded.
  let wasmReady = false;

  async function tryLoadWasm() {
    // The shipped WASM verifier (Pyodide build of omnix.receipts.verify)
    // would expose window.__omnix_verify_wasm. See deploy/wasm/README.md.
    if (typeof window !== 'undefined' && window.__omnix_verify_wasm) {
      wasmReady = true;
    }
  }

  window.__omnix_verify = async function(payload) {
    if (!wasmReady) {
      await tryLoadWasm();
    }
    if (wasmReady && window.__omnix_verify_wasm) {
      return await window.__omnix_verify_wasm(payload);
    }
    return await verifyViaServer(payload);
  };
})();
