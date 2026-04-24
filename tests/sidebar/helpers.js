import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { Window } from 'happy-dom';

const INDEX_PATH = join(
  dirname(fileURLToPath(import.meta.url)),
  '../../src/web/index.html',
);

export function readIndexHtml() {
  return readFileSync(INDEX_PATH, 'utf8');
}

/**
 * @param {string} [raw]
 * @returns {Document}
 */
function stripForDomParse(s) {
  return String(s)
    .replace(/<head[\s\S]*?<\/head>/i, '<head><meta charset="utf-8" /></head>')
    .replace(
      /<script[^>]+src=(['"])[^'"]+\1[^>]*>[\s\S]*?<\/script>/gi,
      '<script>/* cdn */</script>',
    )
    .replace(
      /<link[^>]+href=(['"])[^'"]*(?:googleapis|gstatic|cdnjs|jsdelivr|cloudflare)[^'"]*\1[^>]*\/?>\s*/gi,
      '',
    );
}
export function parseIndexDom(raw) {
  const html0 = raw !== undefined ? raw : readIndexHtml();
  return new DOMParser().parseFromString(stripForDomParse(html0), 'text/html');
}

/** Strip all scripts so the DOM is safe to query for #find-box-host / #bottom-bar without double-parsing the big inline script. */
function stripForBodyParse(s) {
  return String(stripForDomParse(s))
    .replace(/<link[^>]+rel=["']?modulepreload["']?[^>]*\/?>(?:\s*)/gi, '')
    .replace(/<script[\s\S]*?<\/script>/gi, '');
}

/**
 * @param {string} [raw]
 * @returns {Document}
 */
export function parseIndexBodyDom(raw) {
  return new DOMParser().parseFromString(
    stripForBodyParse(raw !== undefined ? raw : readIndexHtml()),
    'text/html',
  );
}

export const OMNIX_FIND_POS_KEY = 'omnix.find.position';

/**
 * @param {string} html
 * @returns {string | null}
 */
export function extractFindIifeString(html) {
  const a = html.indexOf('// OMNIX_FINDBOX_IIFE_START');
  if (a === -1) {
    return null;
  }
  const b = html.indexOf('// OMNIX_FINDBOX_IIFE_END', a);
  if (b === -1) {
    return null;
  }
  const block = html.slice(a, b);
  const f = block.indexOf('(function');
  if (f === -1) {
    return null;
  }
  return block.slice(f).trim();
}

/**
 * @param {object} opts
 * @param {number} [opts.width]
 * @param {number} [opts.height]
 * @param {{ x: number, y: number } | null | undefined} [opts.savedPosition] — stored localStorage; omit/undefined to clear
 * @param {boolean} [opts.skipIife] — for DOM-only checks
 * @param {boolean} [opts.reducedMotion] — `prefers-reduced-motion: reduce` for @media
 * @returns {import('happy-dom').Window}
 */
export function newFindTestWindow(opts = {}) {
  const { width = 800, height = 600, savedPosition, skipIife, reducedMotion } = opts;
  const raw = readIndexHtml();
  const styleMatch = raw.match(/<style>[\s\S]*?<\/style>/);
  const style = styleMatch ? styleMatch[0] : '<style></style>';
  const doc = parseIndexBodyDom(raw);
  const find = doc.getElementById('find-box-host') || doc.getElementById('search-panel-wrap');
  const bar = doc.getElementById('bottom-bar');
  if (!find || !bar) {
    const w = new Window();
    w.document.write('<!DOCTYPE html><html><head></head><body></body></html>');
    w.document.close();
    return w;
  }
  const btn = doc.getElementById('btn-vault');
  const iife = extractFindIifeString(raw);
  const win = new Window();
  try {
    win.localStorage.removeItem(OMNIX_FIND_POS_KEY);
  } catch (e) {
    /* */
  }
  const vdim = { w: width, h: height };
  Object.defineProperty(win, 'innerWidth', {
    get: () => vdim.w,
    set: (v) => {
      vdim.w = v;
    },
    configurable: true,
    enumerable: true,
  });
  Object.defineProperty(win, 'innerHeight', {
    get: () => vdim.h,
    set: (v) => {
      vdim.h = v;
    },
    configurable: true,
    enumerable: true,
  });
  try {
    win.outerWidth = width;
  } catch {
    /* */
  }
  if (reducedMotion === true) {
    applyReducedMotionQuery(win, true);
  }
  if (savedPosition && typeof savedPosition.x === 'number' && typeof savedPosition.y === 'number') {
    win.localStorage.setItem(OMNIX_FIND_POS_KEY, JSON.stringify(savedPosition));
  } else {
    win.localStorage.removeItem(OMNIX_FIND_POS_KEY);
  }
  const nw = String(Number(width) || 800);
  const nh = String(Number(height) || 600);
  let findHtml = find.outerHTML;
  if (findHtml.includes('id="find-box-host"')) {
    findHtml = findHtml.replace(
      'id="find-box-host"',
      'id="find-box-host" data-omnix-vw="' + nw + '" data-omnix-vh="' + nh + '"',
    );
  }
  let bodyInner = findHtml + bar.outerHTML;
  if (btn) {
    if (bar.contains(btn) || find.contains(btn)) {
      /* */
    } else {
      bodyInner += btn.outerHTML;
    }
  } else {
    bodyInner += '<button type="button" id="btn-vault" hidden=""></button>';
  }
  win.document.write(
    '<!DOCTYPE html><html><head><meta charset="utf-8" />' +
      style +
      '</head><body style="margin:0">' +
      bodyInner +
      '</body></html>',
  );
  win.document.close();
  vdim.w = width;
  vdim.h = height;
  try {
    if (win.document && win.document.documentElement) {
      const el = win.document.documentElement;
      if (el.style) {
        el.style.minWidth = width + 'px';
        el.style.width = width + 'px';
        el.style.minHeight = height + 'px';
      }
    }
  } catch (e) {
    /* */
  }
  if (typeof (/** @type {{ PointerEvent?: typeof PointerEvent }} */ (win)).PointerEvent !== 'function' && win.MouseEvent) {
    win.PointerEvent = class P extends win.MouseEvent {
      /** @param {string} type @param {import('happy-dom').PointerEventInit} [init] */
      constructor(type, init) {
        super(
          type,
          init
            ? {
                bubbles: init.bubbles,
                cancelable: init.cancelable,
                clientX: init.clientX,
                clientY: init.clientY,
                button: init.button,
              }
            : undefined,
        );
        this.pointerId = (init && init.pointerId) || 0;
        this.pointerType = (init && init.pointerType) || 'mouse';
      }
    };
  }
  if (iife && !skipIife) {
    if (!win.document.getElementById('find-box-host')) {
      throw new Error('newFindTestWindow: #find-box-host missing from DOM (fragment parse mismatch)');
    }
    const scr = win.document.createElement('script');
    scr.textContent = iife;
    win.document.body.appendChild(scr);
  }
  win.dispatchEvent(new win.Event('resize', { bubbles: true }));
  return win;
}

/**
 * @param {string} html
 * @returns {string}
 */
export function extractSidebarCssText(html) {
  const s = '/* === SIDEBAR (Integration #3.5) === */';
  const i = html.indexOf(s);
  if (i === -1) return '';
  const rest = html.slice(i);
  const e = rest.indexOf('  </style>');
  if (e === -1) return '';
  return rest.slice(0, e);
}

/**
 * @param {string} html
 * @returns {string}
 */
export function extractSidebarBodyInner(html) {
  const a = '<!-- === SIDEBAR (Integration #3.5) === -->';
  const i0 = html.indexOf(a);
  if (i0 === -1) return '';
  const from = i0 + a.length;
  const j = html.indexOf('  <script>\n', from);
  if (j === -1) return '';
  return html.slice(from, j).trim();
}

/**
 * @param {string} html
 * @returns {string | null}
 */
export function extractSidebarIifeString(html) {
  const a = html.indexOf('// OMNIX_SIDEBAR_IIFE_START');
  if (a === -1) return null;
  const b = html.indexOf('// OMNIX_SIDEBAR_IIFE_END', a);
  if (b === -1) return null;
  const block = html.slice(a, b);
  const f = block.indexOf('(function');
  if (f === -1) return null;
  return block.slice(f).trim();
}

/**
 * @param {Window} win
 * @param {number} width
 */
function setWindowInnerWidth(win, width) {
  Object.defineProperty(win, 'innerWidth', { value: width, configurable: true });
  Object.defineProperty(win, 'innerHeight', { value: 800, configurable: true });
  try {
    Object.defineProperty(win, 'outerWidth', { value: width, configurable: true });
  } catch {
    /* */
  }
}

/**
 * @param {Window} win
 * @param {boolean} [reduce]
 */
export function applyReducedMotionQuery(win, reduce) {
  const o = { matches: reduce === true, addEventListener: () => {}, removeEventListener: () => {} };
  const original = win.matchMedia.bind(win);
  win.matchMedia = (q) => {
    if (String(q).includes('prefers-reduced-motion')) {
      return o;
    }
    return original(q);
  };
}

/**
 * Mounts sidebar HTML + CSS + IIFE in a new happy-dom window for interaction tests.
 * @param {object} opts
 * @param {number} [opts.width]
 * @param {string} [opts.html]
 * @param {boolean} [opts.reducedMotion]
 * @param {() => any} [opts.mockFetch]
 * @returns {Window}
 */
export function newSidebarTestWindow(opts = {}) {
  const { width = 1280, html: overrideHtml, reducedMotion, mockFetch } = opts;
  const raw = overrideHtml !== undefined ? overrideHtml : readIndexHtml();
  const css = extractSidebarCssText(raw);
  const body = extractSidebarBodyInner(raw);
  const iife = extractSidebarIifeString(raw);
  if (!body || !css) {
    const w = new Window();
    w.document.write('<!DOCTYPE html><html><head></head><body></body></html>');
    w.document.close();
    return w;
  }
  const win = new Window();
  setWindowInnerWidth(win, width);
  win.document.write(
    '<!DOCTYPE html><html><head><meta charset="utf-8"><style id="base-r">' +
      'html,body{margin:0;padding:0;height:100%;}' +
      '</style></head><body></body></html>',
  );
  const st = win.document.createElement('style');
  st.textContent = css;
  win.document.head.appendChild(st);
  win.document.body.insertAdjacentHTML('beforeend', body);
  if (!win.document.getElementById('btn-vault')) {
    const b = win.document.createElement('button');
    b.id = 'btn-vault';
    b.type = 'button';
    b.textContent = '🔐 AI Keys';
    win.document.body.appendChild(b);
  }
  if (reducedMotion === true) {
    applyReducedMotionQuery(win, true);
  }
  if (typeof mockFetch === 'function') {
    win.fetch = /** @type {Window['fetch']} */ (mockFetch);
  }
  if (iife) {
    if (win.eval) {
      win.eval(iife);
    } else {
      const scr = win.document.createElement('script');
      scr.textContent = iife;
      win.document.body.appendChild(scr);
    }
  }
  if (width != null) {
    win.dispatchEvent(
      new win.Event('resize', { bubbles: true, cancelable: true }),
    );
  }
  return win;
}
