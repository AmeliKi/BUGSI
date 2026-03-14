const API_BASE = '/api'

// Track whether we have an active session (set after successful login/refresh, cleared on logout)
let hasSession = false

export function setLoggedIn() {
  hasSession = true
}

export function setLoggedOut() {
  hasSession = false
}

export function isLoggedIn(): boolean {
  return hasSession
}

// Deduplicate concurrent refresh attempts
let refreshPromise: Promise<boolean> | null = null

async function refreshAccessToken(): Promise<boolean> {
  if (refreshPromise) return refreshPromise
  refreshPromise = doRefresh().finally(() => {
    refreshPromise = null
  })
  return refreshPromise
}

async function doRefresh(): Promise<boolean> {
  if (!hasSession) return false
  try {
    const resp = await fetch(`${API_BASE}/auth/refresh`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    })
    if (!resp.ok) return false
    return true
  } catch {
    return false
  }
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit & { signal?: AbortSignal } = {},
): Promise<{ data: T; headers: Headers }> {
  const headers = new Headers(options.headers)
  if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }

  let resp = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
    credentials: 'include',
  })

  if (resp.status === 401 && hasSession) {
    const refreshed = await refreshAccessToken()
    if (refreshed) {
      resp = await fetch(`${API_BASE}${path}`, {
        ...options,
        headers,
        credentials: 'include',
      })
    }
  }

  if (!resp.ok) {
    const error = await resp.json().catch(() => ({ detail: resp.statusText }))
    throw new Error(error.detail || `HTTP ${resp.status}`)
  }

  if (resp.status === 204) {
    return { data: undefined as T, headers: resp.headers }
  }

  const data = await resp.json()
  return { data, headers: resp.headers }
}
