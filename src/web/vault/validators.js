/**
 * Live API key validation against provider endpoints. Keys go only browser → provider.
 * Compliance: P2, P15, P16, P18 (structured errors; no key in messages)
 */
// Compliance: P16, P18

/**
 * @typedef {'anthropic'|'openai'|'google'|'ollama'|'xai'|'groq'|'perplexity'|'openrouter'|'deepseek'|'mistral'|'cohere'|'together'|'fireworks'|'replicate'|'huggingface'|'cerebras'|'custom_openai'} VaultProvider
 */

/**
 * @param {string} errorMessage Safe non-secret description
 * @returns {{ ok: false, error: string }}
 */
function fail(errorMessage) {
  return { ok: false, error: errorMessage };
}

/**
 * @param {string} name Safe provider tag for error strings (no key material)
 * @param {string} url Full URL for GET
 * @returns {Promise<{ ok: true }|{ ok: false, error: string }>}
 */
export function makeBearerValidator(name, url) {
  return async function validateKey(keyValue) {
    try {
      const r = await fetch(url, {
        method: 'GET',
        headers: { authorization: `Bearer ${keyValue}` },
      });
      if (r.ok) return { ok: true };
      return fail(`${name}: ${r.status}`);
    } catch (e) {
      // eslint-disable-next-line no-console
      console.error(`omnix_vault: ${name} validation request failed`);
      return fail(`${name}: network error`);
    }
  };
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
 * Ollama "key" is the server base URL.
 * @param {string} keyValue
 * @returns {Promise<{ ok: true }|{ ok: false, error: string }>}
 */
export async function validateOllamaKey(keyValue) {
  let u = String(keyValue || '').trim();
  if (!u) u = 'http://127.0.0.1:11434';
  u = u.replace(/\/$/, '');
  return validateOllamaBase(u);
}

const validateXai = makeBearerValidator('xai', 'https://api.x.ai/v1/models');
const validateGroq = makeBearerValidator('groq', 'https://api.groq.com/openai/v1/models');
const validateOpenrouter = makeBearerValidator('openrouter', 'https://openrouter.ai/api/v1/models');
const validateDeepseek = makeBearerValidator('deepseek', 'https://api.deepseek.com/v1/models');
const validateMistral = makeBearerValidator('mistral', 'https://api.mistral.ai/v1/models');
const validateTogether = makeBearerValidator('together', 'https://api.together.xyz/v1/models');
const validateFireworks = makeBearerValidator('fireworks', 'https://api.fireworks.ai/inference/v1/models');
const validateCerebras = makeBearerValidator('cerebras', 'https://api.cerebras.ai/v1/models');

export { validateXai, validateGroq, validateOpenrouter, validateDeepseek, validateMistral, validateTogether, validateFireworks, validateCerebras };

/**
 * Perplexity: no public GET /models; minimal chat completion.
 * @param {string} keyValue
 * @returns {Promise<{ ok: true }|{ ok: false, error: string }>}
 */
export async function validatePerplexityKey(keyValue) {
  try {
    const r = await fetch('https://api.perplexity.ai/chat/completions', {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        authorization: `Bearer ${keyValue}`,
      },
      body: JSON.stringify({
        model: 'sonar',
        max_tokens: 1,
        messages: [{ role: 'user', content: '.' }],
      }),
    });
    if (r.ok) return { ok: true };
    return fail(`perplexity: ${r.status}`);
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error('omnix_vault: perplexity validation request failed');
    return fail('perplexity: network error');
  }
}

/**
 * @param {string} keyValue
 * @returns {Promise<{ ok: true }|{ ok: false, error: string }>}
 */
export async function validateCohereKey(keyValue) {
  try {
    const r = await fetch('https://api.cohere.ai/v1/models', {
      method: 'GET',
      headers: { authorization: `Bearer ${keyValue}` },
    });
    if (r.ok) return { ok: true };
    return fail(`cohere: ${r.status}`);
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error('omnix_vault: cohere validation request failed');
    return fail('cohere: network error');
  }
}

/**
 * @param {string} keyValue
 * @returns {Promise<{ ok: true }|{ ok: false, error: string }>}
 */
export async function validateReplicateKey(keyValue) {
  try {
    const r = await fetch('https://api.replicate.com/v1/models', {
      method: 'GET',
      headers: { authorization: `Token ${keyValue}` },
    });
    if (r.ok) return { ok: true };
    return fail(`replicate: ${r.status}`);
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error('omnix_vault: replicate validation request failed');
    return fail('replicate: network error');
  }
}

/**
 * @param {string} keyValue
 * @returns {Promise<{ ok: true }|{ ok: false, error: string }>}
 */
export async function validateHuggingfaceKey(keyValue) {
  try {
    const r = await fetch('https://huggingface.co/api/whoami-v2', {
      method: 'GET',
      headers: { authorization: `Bearer ${keyValue}` },
    });
    if (r.ok) return { ok: true };
    return fail(`huggingface: ${r.status}`);
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error('omnix_vault: huggingface validation request failed');
    return fail('huggingface: network error');
  }
}

/**
 * @param {string} keyValue
 * @param {string} baseUrl e.g. https://host:port/v1
 * @returns {Promise<{ ok: true }|{ ok: false, error: string }>}
 */
export async function validateCustomOpenAiCompat(keyValue, baseUrl) {
  const b = String(baseUrl || '').trim().replace(/\/$/, '');
  if (!b) {
    return fail('custom: base URL required');
  }
  const u = `${b}/models`;
  try {
    const r = await fetch(u, {
      method: 'GET',
      headers: { authorization: `Bearer ${keyValue}` },
    });
    if (r.ok) return { ok: true };
    return fail(`custom: ${r.status}`);
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error('omnix_vault: custom OpenAI-compatible validation request failed');
    return fail('custom: network error');
  }
}

/**
 * @param {string} p
 * @param {string} keyValue
 * @param {{ base_url?: string }} [opts]
 * @returns {Promise<{ ok: true }|{ ok: false, error: string }>}
 */
async function dispatch(p, keyValue, opts) {
  switch (p) {
    case 'anthropic':
      return validateAnthropicKey(keyValue);
    case 'openai':
      return validateOpenAiKey(keyValue);
    case 'google':
      return validateGoogleKey(keyValue);
    case 'ollama':
      return validateOllamaKey(keyValue);
    case 'xai':
      return validateXai(keyValue);
    case 'groq':
      return validateGroq(keyValue);
    case 'perplexity':
      return validatePerplexityKey(keyValue);
    case 'openrouter':
      return validateOpenrouter(keyValue);
    case 'deepseek':
      return validateDeepseek(keyValue);
    case 'mistral':
      return validateMistral(keyValue);
    case 'cohere':
      return validateCohereKey(keyValue);
    case 'together':
      return validateTogether(keyValue);
    case 'fireworks':
      return validateFireworks(keyValue);
    case 'replicate':
      return validateReplicateKey(keyValue);
    case 'huggingface':
      return validateHuggingfaceKey(keyValue);
    case 'cerebras':
      return validateCerebras(keyValue);
    case 'custom_openai':
      return validateCustomOpenAiCompat(keyValue, opts && opts.base_url ? String(opts.base_url) : '');
    default:
      return fail('unknown provider');
  }
}

/**
 * @param {VaultProvider | string} provider
 * @param {string} keyValue For ollama: base URL; for custom_openai: key + base_url in opts
 * @param {{ base_url?: string }} [opts] Required for custom_openai
 * @returns {Promise<{ ok: true }|{ ok: false, error: string }>}
 */
export async function validateProviderKey(provider, keyValue, opts) {
  const p = String(provider);
  if (p === 'custom_openai') {
    const b = opts && String(opts.base_url || '').trim();
    if (!b) {
      return fail('custom: base URL required');
    }
  }
  return dispatch(p, keyValue, opts);
}
