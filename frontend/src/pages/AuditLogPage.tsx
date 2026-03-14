import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { type AuditLogEntry, listAuditLogs } from '../api/audit'
import Pagination from '../components/Pagination'
import { formatDate } from '../lib/utils'

const PAGE_SIZE = 20

export default function AuditLogPage() {
  const { t } = useTranslation()
  const [logs, setLogs] = useState<AuditLogEntry[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [actionFilter, setActionFilter] = useState('')
  const [resourceFilter, setResourceFilter] = useState('')

  const load = async (currentOffset = offset) => {
    const filters: { action?: string; resource_type?: string } = {}
    if (actionFilter) filters.action = actionFilter
    if (resourceFilter) filters.resource_type = resourceFilter
    const { data, headers } = await listAuditLogs(currentOffset, PAGE_SIZE, filters)
    setLogs(data)
    setTotal(parseInt(headers.get('X-Total-Count') || '0', 10))
  }

  useEffect(() => { load() }, [offset, actionFilter, resourceFilter])

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 mb-6">{t('audit.title')}</h1>

      <div className="flex gap-3 mb-4">
        <select
          value={actionFilter}
          onChange={(e) => { setActionFilter(e.target.value); setOffset(0) }}
          className="px-3 py-2 border rounded-md text-sm"
        >
          <option value="">{t('audit.filter.all_actions')}</option>
          {['create', 'update', 'deactivate', 'activate', 'delete', 'deploy', 'upload', 'build', 'regenerate_key', 'change_password'].map((a) => (
            <option key={a} value={a}>{a}</option>
          ))}
        </select>
        <select
          value={resourceFilter}
          onChange={(e) => { setResourceFilter(e.target.value); setOffset(0) }}
          className="px-3 py-2 border rounded-md text-sm"
        >
          <option value="">{t('audit.filter.all_resources')}</option>
          {['user', 'device', 'ota_package', 'ota_deployment'].map((r) => (
            <option key={r} value={r}>{r}</option>
          ))}
        </select>
      </div>

      <div className="bg-white rounded-lg border">
        <table className="w-full text-sm">
          <thead className="bg-gray-50">
            <tr>
              <th className="text-left px-4 py-2 font-medium text-gray-500">{t('audit.table.timestamp')}</th>
              <th className="text-left px-4 py-2 font-medium text-gray-500">{t('audit.table.actor')}</th>
              <th className="text-left px-4 py-2 font-medium text-gray-500">{t('audit.table.action')}</th>
              <th className="text-left px-4 py-2 font-medium text-gray-500">{t('audit.table.resource_type')}</th>
              <th className="text-left px-4 py-2 font-medium text-gray-500">{t('audit.table.resource_id')}</th>
              <th className="text-left px-4 py-2 font-medium text-gray-500">{t('audit.table.details')}</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {logs.map((entry) => (
              <tr key={entry.id}>
                <td className="px-4 py-2 text-gray-600 whitespace-nowrap">{formatDate(entry.created_at)}</td>
                <td className="px-4 py-2 text-gray-600">{entry.actor_email || '—'}</td>
                <td className="px-4 py-2">
                  <span className="px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800">
                    {entry.action}
                  </span>
                </td>
                <td className="px-4 py-2 text-gray-600">{entry.resource_type}</td>
                <td className="px-4 py-2 text-gray-500 font-mono text-xs">{entry.resource_id ? entry.resource_id.slice(0, 8) + '…' : '—'}</td>
                <td className="px-4 py-2 text-gray-500 text-xs">
                  {entry.details ? JSON.stringify(entry.details) : '—'}
                </td>
              </tr>
            ))}
            {logs.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-gray-400">{t('audit.empty')}</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <Pagination offset={offset} limit={PAGE_SIZE} total={total} onPageChange={setOffset} />
    </div>
  )
}
