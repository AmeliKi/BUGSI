import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import type { User } from '../api/auth'
import { getMe, login as apiLogin, updateMyLanguage } from '../api/auth'
import { apiFetch, setLoggedIn, setLoggedOut } from '../api/client'
import i18n from '../i18n'

interface AuthContextType {
  user: User | null
  isAdmin: boolean
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
  setLanguage: (lang: string) => Promise<void>
}

const AuthContext = createContext<AuthContextType | null>(null)

function syncLanguage(lang: string) {
  i18n.changeLanguage(lang)
  localStorage.setItem('language', lang)
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // Try to restore session via httpOnly cookie (call /me to check)
    getMe()
      .then((u) => {
        setLoggedIn()
        setUser(u)
        syncLanguage(u.language)
      })
      .catch(() => setLoggedOut())
      .finally(() => setLoading(false))
  }, [])

  const login = async (email: string, password: string) => {
    const u = await apiLogin(email, password)
    setUser(u)
    syncLanguage(u.language)
  }

  const logout = () => {
    apiFetch('/auth/logout', { method: 'POST' }).catch(() => {})
    setLoggedOut()
    setUser(null)
  }

  const setLanguage = async (lang: string) => {
    syncLanguage(lang)
    if (user) {
      const updated = await updateMyLanguage(lang)
      setUser(updated)
    }
  }

  return (
    <AuthContext.Provider value={{ user, isAdmin: user?.role === 'admin', loading, login, logout, setLanguage }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
