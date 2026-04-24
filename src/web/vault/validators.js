/**
 * Live API key validation against provider endpoints. Keys go only browser → provider.
 * Compliance: P2, P15, P16, P18 (structured errors; no key in messages)
 */
// Compliance: P16, P18

/**
 * @typedef {'anthropic'|'openai'|'google'|'ollama'} VaultProvider
 */

/**
 * @param {string} errorMessage Safe non-secret description
 * @returns {{ ok: false, error: string }}
 */
function fail(errorMessage) {
  return { ok: false, error: errorMessage };
}

/**
 * @param {string} keyValue
 * @returns {Promise<{ ok: true }|{ ok: false, error: string }>}
 */
export async function validateAnthropicKey(keyValue) {
  try {
    const r = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'anthropic-version': '2023-06-01',
        'x-api-key': keyValue,
      },
      body: JSON.stringify({
        model: 'claude-haiku-4-5',
        max_tokens: 1,
        messages: [{ role: 'user', content: 'x' }],
      }),
    });
    if (r.ok) return { ok: true };
    return fail(`anthropic: ${r.status}`);
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error('omnix_vault: anthropic validation request failed');
    return fail('anthropic: network error');
  }
}

/**
 * @param {string} keyValue
 * @returns {Promise<{ ok: true }|{ ok: false, error: string }>}
 */
export async function validateOpenAiKey(keyValue) {
  try {
    const r = await fetch('https://api.openai.com/v1/models', {
      method: 'GET',
      headers: { authorization: `Bearer ${keyValue}` },
    });
    if (r.ok) return { ok: true };
    return fail(`openai: ${r.status}`);
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error('omnix_vault: openai validation request failed');
    return fail('openai: network error');
  }
}

/**
 * @param {string} keyValue
 * @returns {Promise<{ ok: true }|{ ok: false, error: string }>}
 */
export async function validateGoogleKey(keyValue) {
  try {
    const u = new URL('https://generativelanguage.googleapis.com/v1beta/models');
    u.searchParams.set('key', keyValue);
    const r = await fetch(u.toString(), { method: 'GET' });
    if (r.ok) return { ok: true };
    return fail(`google: ${r.status}`);
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error('omnix_vault: google validation request failed');
    return fail('google: network error');
  }
}

/**
 * @param {string} baseUrl Normalized base URL (no trailing slash)
 * @returns {Promise<{ ok: true }|{ ok: false, error: string }>}
 */
export async function validateOllamaBase(baseUrl) {
  try {
    const u = `${baseUrl}/api/tags`;
    const r = await fetch(u, { method: 'GET' });
    if (r.ok) return { ok: true };
    return fail(`ollama: ${r.status}`);
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error('omnix_vault: ollama validation request failed');
    return fail('ollama: network error');
  }
}

/**
 * @param {VaultProvider} provider
 * @param {string} keyValue For ollama: base URL of the server
 * @returns {Promise<{ ok: true }|{ ok: false, error: string }>}
 */
export async function validateProviderKey(provider, keyValue) {
  if (provider === 'anthropic') return validateAnthropicKey(keyValue);
  if (provider === 'openai') return validateOpenAiKey(keyValue);
  if (provider === 'google') return validateGoogleKey(keyValue);
  if (provider === 'ollama') {
    let u = String(keyValue || '').trim();
    if (!u) u = 'http://127.0.0.1:11434';
    u = u.replace(/\/$/, '');
    return validateOllamaBase(u);
  }
  return fail('unknown provider');
}
