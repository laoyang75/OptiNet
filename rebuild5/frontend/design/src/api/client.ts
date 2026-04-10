export interface ApiError {
  code: string
  message: string
}

export interface ApiEnvelope<T> {
  data: T
  meta: Record<string, unknown>
  error: ApiError | null
}

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://127.0.0.1:47231'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    ...init,
  })

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`)
  }

  const envelope = await response.json() as ApiEnvelope<T>
  if (envelope.error) {
    throw new Error(envelope.error.message)
  }
  return envelope.data
}

export interface PageMeta {
  page: number
  page_size: number
  total_count: number
  total_pages: number
}

export interface PagedResult<T> {
  data: T
  meta: PageMeta
}

export function apiGet<T>(path: string): Promise<T> {
  return request<T>(path)
}

export async function apiGetPaged<T>(path: string): Promise<PagedResult<T>> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
  })
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  const envelope = await response.json() as ApiEnvelope<T>
  if (envelope.error) throw new Error(envelope.error.message)
  return {
    data: envelope.data,
    meta: envelope.meta as unknown as PageMeta,
  }
}

export function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    body: body === undefined ? undefined : JSON.stringify(body),
  })
}
