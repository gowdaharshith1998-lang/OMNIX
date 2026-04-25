/**
 * Single source of truth: LLM provider catalog, detection, and UI copy.
 * @module
 */
// Compliance: P16, P22 — never log or echo key material from here

import {
  validateAnthropicKey,
  validateOpenAiKey,
  validateGoogleKey,
  validateOllamaKey,
  validateXai,
  validateGroq,
  validatePerplexityKey,
  validateOpenrouter,
  validateDeepseek,
  validateMistral,
  validateCohereKey,
  validateReplicateKey,
  validateHuggingfaceKey,
  validateCerebras,
  validateFireworks,
  validateTogether,
  validateCustomOpenAiCompat,
} from './validators.js';

/**
 * @typedef {Object} ProviderDef
 * @property {string} id
 * @property {string} display
 * @property {RegExp[]} keyPatterns
 * @property {number} priority
 * @property {string} keyPrefix
 * @property {boolean} isOpenAiCompat
 * @property {string} validateUrl
 * @property {'GET'|'POST'} validateMethod
 * @property {(key: string, baseUrl?: string) => Promise<{ok:true}|{ok:false,error:string}>} validate
 */

/**
 * @type {Record<string, ProviderDef & { valueProp: string, letter: string, circle: string, displayName: string }>}
 */
export const PROVIDERS = {
  anthropic: {
    id: 'anthropic',
    display: 'Anthropic (Claude)',
    displayName: 'Anthropic',
    valueProp: 'Claude models',
    letter: 'A',
    circle: '#f97316',
    keyPatterns: [/^sk-ant-api\d{2}-[\w-]{32,}$/i],
    priority: 90,
    keyPrefix: 'sk-ant-',
    isOpenAiCompat: false,
    validateUrl: 'https://api.anthropic.com/v1/messages',
    validateMethod: 'POST',
    validate: validateAnthropicKey,
  },
  openai: {
    id: 'openai',
    display: 'OpenAI (GPT)',
    displayName: 'OpenAI',
    valueProp: 'GPT models',
    letter: 'O',
    circle: '#22c55e',
    keyPatterns: [/^sk-proj-[\w-]{20,}$/i, /^sk-[A-Za-z0-9]{20,}$/],
    priority: 70,
    keyPrefix: 'sk-',
    isOpenAiCompat: true,
    validateUrl: 'https://api.openai.com/v1/models',
    validateMethod: 'GET',
    validate: validateOpenAiKey,
  },
  google: {
    id: 'google',
    display: 'Google (Gemini)',
    displayName: 'Google',
    valueProp: 'Gemini models',
    letter: 'G',
    circle: '#3b82f6',
    keyPatterns: [/^AIza[\w-]{35,}$/],
    priority: 95,
    keyPrefix: 'AIza',
    isOpenAiCompat: false,
    validateUrl: 'https://generativelanguage.googleapis.com/v1beta/models',
    validateMethod: 'GET',
    validate: validateGoogleKey,
  },
  ollama: {
    id: 'ollama',
    display: 'Ollama (local)',
    displayName: 'Ollama',
    valueProp: 'Run models on your machine',
    letter: 'L',
    circle: '#a855f7',
    keyPatterns: [/^https?:\/\//i],
    priority: 80,
    keyPrefix: 'http://',
    isOpenAiCompat: false,
    validateUrl: '',
    validateMethod: 'GET',
    validate: validateOllamaKey,
  },
  xai: {
    id: 'xai',
    display: 'xAI (Grok)',
    displayName: 'xAI',
    valueProp: 'Grok models',
    letter: 'X',
    circle: '#eab308',
    keyPatterns: [/^xai-[\w-]{32,}$/i],
    priority: 95,
    keyPrefix: 'xai-',
    isOpenAiCompat: true,
    validateUrl: 'https://api.x.ai/v1/models',
    validateMethod: 'GET',
    validate: validateXai,
  },
  groq: {
    id: 'groq',
    display: 'Groq',
    displayName: 'Groq',
    valueProp: 'Fast inference',
    letter: 'Q',
    circle: '#f472b6',
    keyPatterns: [/^gsk_[\w]{40,}$/i],
    priority: 95,
    keyPrefix: 'gsk_',
    isOpenAiCompat: true,
    validateUrl: 'https://api.groq.com/openai/v1/models',
    validateMethod: 'GET',
    validate: validateGroq,
  },
  perplexity: {
    id: 'perplexity',
    display: 'Perplexity',
    displayName: 'Perplexity',
    valueProp: 'Search-augmented chat',
    letter: 'P',
    circle: '#14b8a6',
    keyPatterns: [/^pplx-[\w]{40,}$/i],
    priority: 95,
    keyPrefix: 'pplx-',
    isOpenAiCompat: true,
    validateUrl: 'https://api.perplexity.ai',
    validateMethod: 'POST',
    validate: validatePerplexityKey,
  },
  openrouter: {
    id: 'openrouter',
    display: 'OpenRouter',
    displayName: 'OpenRouter',
    valueProp: 'Multi-vendor API',
    letter: 'R',
    circle: '#8b5cf6',
    keyPatterns: [/^sk-or-v1-[\w]{40,}$/i],
    priority: 95,
    keyPrefix: 'sk-or-v1-',
    isOpenAiCompat: true,
    validateUrl: 'https://openrouter.ai/api/v1/models',
    validateMethod: 'GET',
    validate: validateOpenrouter,
  },
  deepseek: {
    id: 'deepseek',
    display: 'DeepSeek',
    displayName: 'DeepSeek',
    valueProp: 'DeepSeek API',
    letter: 'D',
    circle: '#0ea5e9',
    keyPatterns: [/^sk-[a-f0-9]{32}$/i],
    priority: 60,
    keyPrefix: 'sk-',
    isOpenAiCompat: true,
    validateUrl: 'https://api.deepseek.com/v1/models',
    validateMethod: 'GET',
    validate: validateDeepseek,
  },
  mistral: {
    id: 'mistral',
    display: 'Mistral',
    displayName: 'Mistral',
    valueProp: 'Mistral models',
    letter: 'M',
    circle: '#f43f5e',
    keyPatterns: [/^[a-zA-Z0-9]{32}$/],
    priority: 30,
    keyPrefix: '',
    isOpenAiCompat: true,
    validateUrl: 'https://api.mistral.ai/v1/models',
    validateMethod: 'GET',
    validate: validateMistral,
  },
  cohere: {
    id: 'cohere',
    display: 'Cohere',
    displayName: 'Cohere',
    valueProp: 'Cohere models',
    letter: 'C',
    circle: '#a78bfa',
    keyPatterns: [/^[a-zA-Z0-9]{40}$/],
    priority: 30,
    keyPrefix: '',
    isOpenAiCompat: false,
    validateUrl: 'https://api.cohere.ai/v1/models',
    validateMethod: 'GET',
    validate: validateCohereKey,
  },
  together: {
    id: 'together',
    display: 'Together AI',
    displayName: 'Together',
    valueProp: 'Open models cloud',
    letter: 'T',
    circle: '#f97316',
    keyPatterns: [/^[a-f0-9]{64}$/i],
    priority: 50,
    keyPrefix: '',
    isOpenAiCompat: true,
    validateUrl: 'https://api.together.xyz/v1/models',
    validateMethod: 'GET',
    validate: validateTogether,
  },
  fireworks: {
    id: 'fireworks',
    display: 'Fireworks AI',
    displayName: 'Fireworks',
    valueProp: 'Serverless inference',
    letter: 'F',
    circle: '#ef4444',
    keyPatterns: [/^fw_[\w]{20,}$/i],
    priority: 95,
    keyPrefix: 'fw_',
    isOpenAiCompat: true,
    validateUrl: 'https://api.fireworks.ai/inference/v1/models',
    validateMethod: 'GET',
    validate: validateFireworks,
  },
  replicate: {
    id: 'replicate',
    display: 'Replicate',
    displayName: 'Replicate',
    valueProp: 'Hosted models',
    letter: 'N',
    circle: '#ec4899',
    keyPatterns: [/^r8_[\w]{30,}$/i],
    priority: 95,
    keyPrefix: 'r8_',
    isOpenAiCompat: false,
    validateUrl: 'https://api.replicate.com/v1/models',
    validateMethod: 'GET',
    validate: validateReplicateKey,
  },
  huggingface: {
    id: 'huggingface',
    display: 'Hugging Face',
    displayName: 'Hugging Face',
    valueProp: 'Hub & Inference',
    letter: 'H',
    circle: '#ffd21e',
    keyPatterns: [/^hf_[\w]{30,}$/i],
    priority: 95,
    keyPrefix: 'hf_',
    isOpenAiCompat: false,
    validateUrl: 'https://huggingface.co',
    validateMethod: 'GET',
    validate: validateHuggingfaceKey,
  },
  cerebras: {
    id: 'cerebras',
    display: 'Cerebras',
    displayName: 'Cerebras',
    valueProp: 'Cerebras API',
    letter: 'B',
    circle: '#22d3ee',
    keyPatterns: [/^csk-[\w]{30,}$/i],
    priority: 95,
    keyPrefix: 'csk-',
    isOpenAiCompat: true,
    validateUrl: 'https://api.cerebras.ai/v1/models',
    validateMethod: 'GET',
    validate: validateCerebras,
  },
  custom_openai: {
    id: 'custom_openai',
    display: 'Custom (OpenAI-compatible)',
    displayName: 'Custom',
    valueProp: 'vLLM, LM Studio, LocalAI, self-hosted',
    letter: '+',
    circle: '#64748b',
    keyPatterns: [],
    priority: 0,
    keyPrefix: '',
    isOpenAiCompat: true,
    validateUrl: '',
    validateMethod: 'GET',
    validate: (key, base) => validateCustomOpenAiCompat(key, base || ''),
  },
};

/** @type {readonly string[]} */
export const POPULAR_PROVIDER_IDS = Object.freeze([
  'anthropic',
  'openai',
  'google',
  'groq',
  'openrouter',
  'xai',
]);

const CUSTOM = 'custom_openai';

/**
 * Ids in grid order: detected (optional), popular, more (by displayName), then custom.
 * @param {string | null} [detectedId]
 * @returns {string[]}
 */
export function getGridProviderOrder(detectedId = null) {
  const all = Object.keys(PROVIDERS).filter((k) => k !== CUSTOM);
  const popular = /** @type {string[]} */ (POPULAR_PROVIDER_IDS.filter((id) => PROVIDERS[id]));
  const inPopular = new Set(popular);
  const moreSorted = all
    .filter((id) => !inPopular.has(id))
    .sort((a, b) =>
      String(PROVIDERS[a].displayName).localeCompare(String(PROVIDERS[b].displayName)),
    );
  const out = /** @type {string[]} */ ([]);
  const seen = new Set();
  if (detectedId && PROVIDERS[detectedId] && detectedId !== CUSTOM) {
    out.push(detectedId);
    seen.add(detectedId);
  }
  for (const id of popular) {
    if (!seen.has(id)) {
      out.push(id);
      seen.add(id);
    }
  }
  for (const id of moreSorted) {
    if (!seen.has(id)) {
      out.push(id);
      seen.add(id);
    }
  }
  for (const id of all) {
    if (!seen.has(id)) {
      out.push(id);
      seen.add(id);
    }
  }
  out.push(CUSTOM);
  return out;
}

/**
 * Flat list for tests and introspection: standard providers in catalog order, custom last.
 * @returns {any[]}
 */
export function listProviderDefs() {
  const order = getGridProviderOrder();
  return order.map((id) => PROVIDERS[id]);
}

/**
 * @param {string} keyValue
 * @returns {{ matches: (typeof PROVIDERS)['string'][], confidence: 'exact'|'ambiguous'|'none' }}
 */
export function detectProvider(keyValue) {
  const v = String(keyValue || '').trim();
  if (!v) {
    return { matches: /** @type {any} */ ([]), confidence: 'none' };
  }

  const matched = /** @type {typeof PROVIDERS['string'][]} */ ([]);
  for (const p of Object.values(PROVIDERS)) {
    if (p.id === CUSTOM) {
      continue;
    }
    for (const re of p.keyPatterns) {
      if (re.test(v)) {
        matched.push(p);
        break;
      }
    }
  }

  matched.sort((a, b) => b.priority - a.priority);

  if (matched.length === 0) {
    return { matches: /** @type {any} */ ([]), confidence: 'none' };
  }
  if (matched.length === 1) {
    return { matches: matched, confidence: 'exact' };
  }
  const lead = matched[0].priority - matched[1].priority;
  return {
    matches: matched,
    confidence: lead >= 20 ? 'exact' : 'ambiguous',
  };
}

/**
 * @param {string | null} [detectedId]
 * @returns {{ detected: string[], popular: string[], more: string[], custom: string[] }}
 */
export function getSectionedGridOrder(detectedId) {
  const full = getGridProviderOrder(detectedId);
  const customArr = full[full.length - 1] === CUSTOM ? [CUSTOM] : [CUSTOM];
  if (full.length < 1) {
    return { detected: [], popular: [], more: [], custom: customArr };
  }
  const main = full[full.length - 1] === CUSTOM ? full.slice(0, -1) : full;
  const det = /** @type {string[]} */ ([]);
  const rest0 = main.slice();
  if (detectedId && rest0[0] === detectedId) {
    const first = rest0.shift();
    if (first) det.push(first);
  }
  const inPopular = new Set(/** @type {string[]} */ (POPULAR_PROVIDER_IDS.slice()));
  const popular = /** @type {string[]} */ ([]);
  const more = /** @type {string[]} */ ([]);
  for (const id of rest0) {
    if (inPopular.has(id)) popular.push(id);
    else more.push(id);
  }
  return { detected: det, popular, more, custom: customArr };
}

export { validateCustomOpenAiCompat, CUSTOM as PROVIDER_ID_CUSTOM };
