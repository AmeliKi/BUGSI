import { apiFetch } from './client'

export interface AuditLogEntry {
  id: string
  actor_id: string | null
  actor_email: string | null
  action: string
  resource_type: string
  resource_id: string | null
  details: Record<string, unknown> | null
  created_at: string
}

export async function listAuditLogs(
  offset = 0,
  limit = 50,
  filters?: { action?: string; resource_type?: string },
) {
  const params = new URLSearchParams({ offset: String(offset), limit: String(limit) })
  if (filters?.action) params.set('action', filters.action)
  if (filters?.resource_type) params.set('resource_type', filters.resource_type)
  return apiFetch<AuditLogEntry[]>(`/audit-logs?${params}`)
}
