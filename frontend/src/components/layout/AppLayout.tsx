import { Bug, ClipboardList, LayoutDashboard, LogOut, Package, Settings, Users } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import { cn } from '../../lib/utils'
import LanguageSwitcher from '../LanguageSwitcher'

export default function AppLayout() {
  const { t } = useTranslation()
  const { user, isAdmin, logout } = useAuth()
  const location = useLocation()

  const navItems = [
    { to: '/', label: t('nav.dashboard'), icon: LayoutDashboard },
    { to: '/ota', label: t('nav.ota'), icon: Package, adminOnly: true },
    { to: '/users', label: t('nav.users'), icon: Users, adminOnly: true },
    { to: '/audit-logs', label: t('nav.audit_logs'), icon: ClipboardList, adminOnly: true },
    { to: '/settings', label: t('nav.settings'), icon: Settings },
  ]

  return (
    <div className="flex h-screen bg-gray-50">
      <aside className="w-64 bg-white border-r border-gray-200 flex flex-col">
        <div className="p-4 border-b border-gray-200">
          <div className="flex items-center gap-2">
            <Bug className="h-6 w-6 text-green-600" />
            <span className="text-lg font-semibold">{t('app.name')}</span>
          </div>
          <p className="text-xs text-gray-500 mt-1">{t('app.subtitle')}</p>
        </div>

        <nav className="flex-1 p-3 space-y-1">
          {navItems
            .filter((item) => !item.adminOnly || isAdmin)
            .map((item) => (
              <Link
                key={item.to}
                to={item.to}
                className={cn(
                  'flex items-center gap-2 px-3 py-2 rounded-md text-sm transition-colors',
                  location.pathname === item.to
                    ? 'bg-green-50 text-green-700 font-medium'
                    : 'text-gray-600 hover:bg-gray-100',
                )}
              >
                <item.icon className="h-4 w-4" />
                {item.label}
              </Link>
            ))}
        </nav>

        <div className="p-3 border-t border-gray-200">
          <div className="flex items-center justify-between">
            <div className="text-sm">
              <p className="font-medium text-gray-700">{user?.full_name}</p>
              <p className="text-xs text-gray-500">{user?.role}</p>
            </div>
            <div className="flex items-center gap-1">
              <LanguageSwitcher />
              <button
                onClick={logout}
                className="p-2 text-gray-400 hover:text-gray-600 rounded-md hover:bg-gray-100"
                title={t('nav.logout')}
              >
                <LogOut className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
      </aside>

      <main className="flex-1 overflow-auto p-6">
        <Outlet />
      </main>
    </div>
  )
}
