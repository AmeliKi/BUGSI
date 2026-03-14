import { apiFetch, setLoggedIn } from './client'

export interface User {
  id: string
  email: string
  full_name: string
  role: 'admin' | 'user'
  is_active: boolean
  language: string
  created_at: string
  updated_at: string
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

export async function login(email: string, password: string): Promise<User> {
  await apiFetch<TokenResponse>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
  setLoggedIn()
  return getMe()
}

export async function getMe(): Promise<User> {
  const { data } = await apiFetch<User>('/auth/me')
  return data
}

export async function changeMyPassword(currentPassword: string, newPassword: string): Promise<void> {
  await apiFetch<void>('/auth/me/password', {
    method: 'POST',
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  })
}

export async function updateMyLanguage(language: string): Promise<User> {
  const { data } = await apiFetch<User>('/auth/me/language', {
    method: 'PATCH',
    body: JSON.stringify({ language }),
  })
  return data
}
