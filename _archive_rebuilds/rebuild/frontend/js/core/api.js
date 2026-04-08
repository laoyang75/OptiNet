/**
 * fetch 封装、超时、sessionStorage 缓存、失效。
 */

import { API, CACHE_NS } from './state.js';

const memoryCache = new Map();
const inflight = new Map();

function sessionKey(key) {
  return `${CACHE_NS}${key}`;
}

export function getCached(key, ttl) {
  const mem = memoryCache.get(key);
  if (mem && Date.now() - mem.ts < ttl) return mem.data;
  const raw = sessionStorage.getItem(sessionKey(key));
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    if (Date.now() - parsed.ts < ttl) {
      memoryCache.set(key, parsed);
      return parsed.data;
    }
  } catch { /* ignore */ }
  return null;
}

export function setCached(key, data) {
  const payload = { ts: Date.now(), data };
  memoryCache.set(key, payload);
  try {
    sessionStorage.setItem(sessionKey(key), JSON.stringify(payload));
  } catch { /* ignore */ }
}

export function clearApiCache() {
  memoryCache.clear();
  Object.keys(sessionStorage)
    .filter(key => key.startsWith(CACHE_NS))
    .forEach(key => sessionStorage.removeItem(key));
}

export function qs(params = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value != null && value !== '') query.set(key, value);
  });
  const text = query.toString();
  return text ? `?${text}` : '';
}

export async function api(path, {
  ttl = 300000,
  force = false,
  method = 'GET',
  body = null,
} = {}) {
  const key = `${method}:${path}`;
  const isCacheable = method === 'GET' && ttl > 0;
  if (isCacheable && !force) {
    const cached = getCached(key, ttl);
    if (cached != null) return cached;
  }
  if (inflight.has(key)) return inflight.get(key);

  const job = (async () => {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 60000);
    try {
      const response = await fetch(`${API}${path}`, {
        method,
        headers: body ? { 'Content-Type': 'application/json' } : undefined,
        body: body ? JSON.stringify(body) : undefined,
        signal: controller.signal,
      });
      if (!response.ok) {
        const detail = await response.text();
        throw new Error(`${method} ${path} 失败: ${response.status} ${detail}`);
      }
      const data = await response.json();
      if (isCacheable) setCached(key, data);
      return data;
    } finally {
      clearTimeout(timeout);
      inflight.delete(key);
    }
  })();

  inflight.set(key, job);
  return job;
}
