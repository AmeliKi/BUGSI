import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { User } from '../api/auth'
import { createUser, deactivateUser, listUsers, updateUser } from '../api/users'
import Pagination from '../components/Pagination'
import { cn, formatDate } from '../lib/utils'

const PAGE_SIZE = 20

export default function UserManagementPage() {
  const { t } = useTranslation()
  const [users, setUsers] = useState<User[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [showCreate, setShowCreate] = useState(false)

  const load = async (currentOffset = offset) => {
    const { data, headers } = await listUsers(currentOffset, PAGE_SIZE)
    setUsers(data)
    setTotal(parseInt(headers.get('X-Total-Count') || '0', 10))
  }

  useEffect(() => { load() }, [offset])

  const handleCreate = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const form = new FormData(e.currentTarget)
    await createUser({
      email: form.get('email') as string,
      password: form.get('password') as string,
      full_name: form.get('full_name') as string,
      role: form.get('role') as string,
    })
    setShowCreate(false)
    load()
  }

  const handleToggleRole = async (user: User) => {
    await updateUser(user.id, { role: user.role === 'admin' ? 'user' : 'admin' })
    load()
  }

  const handleDeactivate = async (user: User) => {
    if (!confirm(t('users.confirm_deactivate', { name: user.full_name }))) return
    await deactivateUser(user.id)
    load()
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">{t('users.title')}</h1>
        <button
          onClick={() => setShowCreate(!showCreate)}
          className="bg-green-600 text-white px-3 py-2 rounded-md text-sm hover:bg-green-700"
        >
          {t('users.add')}
        </button>
      </div>

      {showCreate && (
        <form onSubmit={handleCreate} className="bg-white border rounded-md p-4 mb-4 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <input name="full_name" required placeholder={t('users.form.full_name')} className="px-3 py-2 border rounded-md text-sm" />
            <input name="email" type="email" required placeholder={t('users.form.email')} className="px-3 py-2 border rounded-md text-sm" />
            <input name="password" type="password" required placeholder={t('users.form.password')} className="px-3 py-2 border rounded-md text-sm" />
            <select name="role" className="px-3 py-2 border rounded-md text-sm">
              <option value="user">{t('users.form.role_user')}</option>
              <option value="admin">{t('users.form.role_admin')}</option>
            </select>
          </div>
          <div className="flex gap-2">
            <button type="submit" className="bg-green-600 text-white px-4 py-2 rounded-md text-sm">{t('users.form.create')}</button>
            <button type="button" onClick={() => setShowCreate(false)} className="px-4 py-2 border rounded-md text-sm">{t('users.form.cancel')}</button>
          </div>
        </form>
      )}

      <div className="bg-white rounded-lg border">
        <table className="w-full text-sm">
          <thead className="bg-gray-50">
            <tr>
              <th className="text-left px-4 py-2 font-medium text-gray-500">{t('users.table.name')}</th>
              <th className="text-left px-4 py-2 font-medium text-gray-500">{t('users.table.email')}</th>
              <th className="text-left px-4 py-2 font-medium text-gray-500">{t('users.table.role')}</th>
              <th className="text-left px-4 py-2 font-medium text-gray-500">{t('users.table.status')}</th>
              <th className="text-left px-4 py-2 font-medium text-gray-500">{t('users.table.created')}</th>
              <th className="text-left px-4 py-2 font-medium text-gray-500">{t('users.table.actions')}</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {users.map((u) => (
              <tr key={u.id}>
                <td className="px-4 py-2 font-medium">{u.full_name}</td>
                <td className="px-4 py-2 text-gray-600">{u.email}</td>
                <td className="px-4 py-2">
                  <span className={cn(
                    'px-2 py-0.5 rounded text-xs font-medium',
                    u.role === 'admin' ? 'bg-purple-100 text-purple-800' : 'bg-blue-100 text-blue-800',
                  )}>
                    {u.role}
                  </span>
                </td>
                <td className="px-4 py-2">
                  <span className={cn(
                    'px-2 py-0.5 rounded text-xs',
                    u.is_active ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-600',
                  )}>
                    {u.is_active ? t('users.status.active') : t('users.status.inactive')}
                  </span>
                </td>
                <td className="px-4 py-2 text-gray-600">{formatDate(u.created_at)}</td>
                <td className="px-4 py-2 space-x-2">
                  <button onClick={() => handleToggleRole(u)} className="text-blue-600 hover:underline text-xs">
                    {u.role === 'admin' ? t('users.action.make_user') : t('users.action.make_admin')}
                  </button>
                  {u.is_active && (
                    <button onClick={() => handleDeactivate(u)} className="text-red-600 hover:underline text-xs">
                      {t('users.action.deactivate')}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Pagination offset={offset} limit={PAGE_SIZE} total={total} onPageChange={setOffset} />
    </div>
  )
}
