import { Check, Copy, Plus, Terminal } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { Device } from '../api/devices'
import { createDevice, listDevices } from '../api/devices'
import DeviceCard from '../components/devices/DeviceCard'
import Pagination from '../components/Pagination'
import { useAuth } from '../context/AuthContext'

const PAGE_SIZE = 12

export default function DashboardPage() {
  const { t } = useTranslation()
  const { isAdmin } = useAuth()
  const [devices, setDevices] = useState<Device[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [showInactive, setShowInactive] = useState(false)
  const [newApiKey, setNewApiKey] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  const load = async (currentOffset = offset) => {
    setLoading(true)
    try {
      const { data, headers } = await listDevices(currentOffset, PAGE_SIZE, showInactive)
      setDevices(data)
      setTotal(parseInt(headers.get('X-Total-Count') || '0', 10))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [offset, showInactive])

  const handleCreate = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const form = new FormData(e.currentTarget)
    const { data } = await createDevice({
      name: form.get('name') as string,
      serial_number: form.get('serial_number') as string,
      location_description: form.get('location_description') as string || undefined,
    })
    setNewApiKey(data.api_key)
    setShowCreate(false)
    load()
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-4">
          <h1 className="text-2xl font-bold text-gray-900">{t('dashboard.title')}</h1>
          <label className="flex items-center gap-1.5 text-sm text-gray-600 cursor-pointer">
            <input
              type="checkbox"
              checked={showInactive}
              onChange={(e) => { setShowInactive(e.target.checked); setOffset(0) }}
              className="rounded border-gray-300"
            />
            {t('dashboard.show_inactive')}
          </label>
        </div>
        {isAdmin && (
          <button
            onClick={() => setShowCreate(!showCreate)}
            className="flex items-center gap-1 bg-green-600 text-white px-3 py-2 rounded-md text-sm hover:bg-green-700"
          >
            <Plus className="h-4 w-4" /> {t('dashboard.add_device')}
          </button>
        )}
      </div>

      {newApiKey && (() => {
        const backendUrl = import.meta.env.VITE_PUBLIC_SERVER_URL || `${window.location.hostname}:8000`
        const onboardCmd = `curl -sfH "X-API-Key: ${newApiKey}" ${backendUrl}/api/device-data/onboard | sudo bash`
        return (
          <div className="space-y-3 mb-4">
            <div className="bg-yellow-50 border border-yellow-200 p-4 rounded-md">
              <p className="text-sm font-medium text-yellow-800 mb-1">{t('dashboard.api_key_warning')}</p>
              <code className="text-xs bg-yellow-100 px-2 py-1 rounded break-all">{newApiKey}</code>
            </div>
            <div className="bg-gray-900 border border-gray-700 p-4 rounded-md">
              <div className="flex items-center gap-2 mb-2">
                <Terminal className="h-4 w-4 text-green-400" />
                <p className="text-sm font-medium text-green-400">{t('dashboard.onboard_title')}</p>
              </div>
              <p className="text-xs text-gray-400 mb-2">{t('dashboard.onboard_description')}</p>
              <div className="flex items-center gap-2">
                <code className="flex-1 text-xs text-gray-100 bg-gray-800 px-3 py-2 rounded font-mono break-all">{onboardCmd}</code>
                <button
                  onClick={() => {
                    navigator.clipboard.writeText(onboardCmd)
                    setCopied(true)
                    setTimeout(() => setCopied(false), 2000)
                  }}
                  className="flex items-center gap-1 px-2 py-2 bg-gray-700 text-gray-200 rounded text-xs hover:bg-gray-600 shrink-0"
                >
                  {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                  {copied ? t('dashboard.onboard_copied') : t('dashboard.onboard_copy')}
                </button>
              </div>
              <p className="text-xs text-gray-500 mt-2">{t('dashboard.onboard_steps')}</p>
            </div>
            <button onClick={() => setNewApiKey(null)} className="text-xs text-gray-500 hover:underline">{t('dashboard.dismiss')}</button>
          </div>
        )
      })()}

      {showCreate && (
        <form onSubmit={handleCreate} className="bg-white border rounded-md p-4 mb-4 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">{t('dashboard.form.name')}</label>
              <input name="name" required className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm" placeholder={t('dashboard.form.name_placeholder')} />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">{t('dashboard.form.serial_number')}</label>
              <input name="serial_number" required className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm" placeholder={t('dashboard.form.serial_placeholder')} />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">{t('dashboard.form.location')}</label>
            <input name="location_description" className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm" placeholder={t('dashboard.form.location_placeholder')} />
          </div>
          <div className="flex gap-2">
            <button type="submit" className="bg-green-600 text-white px-4 py-2 rounded-md text-sm hover:bg-green-700">{t('dashboard.form.create')}</button>
            <button type="button" onClick={() => setShowCreate(false)} className="px-4 py-2 rounded-md text-sm border border-gray-300 hover:bg-gray-50">{t('dashboard.form.cancel')}</button>
          </div>
        </form>
      )}

      {loading ? (
        <p className="text-gray-500">{t('dashboard.loading')}</p>
      ) : devices.length === 0 ? (
        <p className="text-gray-500">{t('dashboard.empty')}</p>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {devices.map((d) => (
              <DeviceCard key={d.id} device={d} />
            ))}
          </div>
          <Pagination offset={offset} limit={PAGE_SIZE} total={total} onPageChange={setOffset} />
        </>
      )}
    </div>
  )
}
