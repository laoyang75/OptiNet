/**
 * fetch 封装、超时、缓存。
 */
import { API, CACHE_NS } from './state.js';

const memoryCache = new Map();
const inflight = new Map();

function sessionKey(key) { return `${CACHE_NS}${key}`; }

export function getCached(key, ttl) {
  const mem = memoryCache.get(key);
  if (mem && Date.now() - mem.ts < ttl) return mem.data;
  const raw = sessionStorage.getItem(sessionKey(key));
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    if (Date.now() - parsed.ts < ttl) { memoryCache.set(key, parsed); return parsed.data; }
  } catch { /* ignore */ }
  return null;
}

export function setCached(key, data) {
  const payload = { ts: Date.now(), data };
  memoryCache.set(key, payload);
  try { sessionStorage.setItem(sessionKey(key), JSON.stringify(payload)); } catch { /* ignore */ }
}

export function clearApiCache() {
  memoryCache.clear();
  Object.keys(sessionStorage).filter(k => k.startsWith(CACHE_NS)).forEach(k => sessionStorage.removeItem(k));
}

export function qs(params = {}) {
  const q = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => { if (v != null && v !== '') q.set(k, v); });
  const s = q.toString();
  return s ? `?${s}` : '';
}

export async function api(path, { ttl = 300000, force = false, method = 'GET', body = null } = {}) {
  const key = `${method}:${path}`;
  const isCacheable = method === 'GET' && ttl > 0;
  if (isCacheable && !force) { const c = getCached(key, ttl); if (c != null) return c; }
  if (inflight.has(key)) return inflight.get(key);

  const job = (async () => {
    const ctrl = new AbortController();
    const timeout = setTimeout(() => ctrl.abort(), 60000);
    try {
      const resp = await fetch(`${API}${path}`, {
        method,
        headers: body ? { 'Content-Type': 'application/json' } : undefined,
        body: body ? JSON.stringify(body) : undefined,
        signal: ctrl.signal,
      });
      if (!resp.ok) { const d = await resp.text(); throw new Error(`${method} ${path} 失败: ${resp.status} ${d}`); }
      const data = await resp.json();
      if (isCacheable) setCached(key, data);
      return data;
    } finally { clearTimeout(timeout); inflight.delete(key); }
  })();
  inflight.set(key, job);
  return job;
}
