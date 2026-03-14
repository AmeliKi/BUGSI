import type { User } from './auth'
import { apiFetch } from './client'

export async function listUsers(offset = 0, limit = 50) {
  return apiFetch<User[]>(`/users?offset=${offset}&limit=${limit}`)
}

export async function createUser(data: { email: string; password: string; full_name: string; role?: string }) {
  return apiFetch<User>('/users', { method: 'POST', body: JSON.stringify(data) })
}

export async function updateUser(id: string, data: { email?: string; full_name?: string; role?: string; is_active?: boolean }) {
  return apiFetch<User>(`/users/${id}`, { method: 'PATCH', body: JSON.stringify(data) })
}

export async function deactivateUser(id: string) {
  return apiFetch<User>(`/users/${id}`, { method: 'DELETE' })
}

export async function setUserDevices(userId: string, deviceIds: string[]) {
  return apiFetch<void>(`/users/${userId}/devices`, {
    method: 'PUT',
    body: JSON.stringify({ device_ids: deviceIds }),
  })
}
