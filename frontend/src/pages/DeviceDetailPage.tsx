import { ArrowLeft, Settings } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useParams } from 'react-router-dom'
import type { Device, TelemetryReading, Thumbnail } from '../api/devices'
import { activateDevice, deactivateDevice, getDevice, getTelemetry, getThumbnails } from '../api/devices'
import TelemetryChart from '../components/devices/TelemetryChart'
import { useAuth } from '../context/AuthContext'
import { cn, formatDate, isOnline } from '../lib/utils'

type Tab = 'telemetry' | 'thumbnails'

export default function DeviceDetailPage() {
  const { t } = useTranslation()
  const { isAdmin } = useAuth()
  const navigate = useNavigate()
  const { deviceId } = useParams<{ deviceId: string }>()
  const [device, setDevice] = useState<Device | null>(null)
  const [tab, setTab] = useState<Tab>('telemetry')
  const [telemetry, setTelemetry] = useState<TelemetryReading[]>([])
  const [thumbnails, setThumbnails] = useState<Thumbnail[]>([])

  useEffect(() => {
    if (!deviceId) return
    getDevice(deviceId).then(({ data }) => setDevice(data))
    getTelemetry(deviceId, { limit: 100 }).then(({ data }) => setTelemetry(data))
    getThumbnails(deviceId, { limit: 30 }).then(({ data }) => setThumbnails(data))
  }, [deviceId])

  if (!device) return <p className="text-gray-500">{t('device.loading')}</p>

  const handleDeactivate = async () => {
    if (!confirm(t('device.confirm_deactivate', { name: device.name }))) return
    await deactivateDevice(device.id)
    navigate('/')
  }

  const handleActivate = async () => {
    await activateDevice(device.id)
    const { data } = await getDevice(device.id)
    setDevice(data)
  }

  const online = isOnline(device.last_seen_at)
  const tabs: { key: Tab; label: string }[] = [
    { key: 'telemetry', label: t('device.tab.telemetry') },
    { key: 'thumbnails', label: `${t('device.tab.thumbnails')} (${thumbnails.length})` },
  ]

  return (
    <div>
      <div className="flex items-center gap-3 mb-6">
        <Link to="/" className="text-gray-400 hover:text-gray-600">
          <ArrowLeft className="h-5 w-5" />
        </Link>
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold text-gray-900">{device.name}</h1>
            <span
              className={cn(
                'px-2 py-0.5 rounded-full text-xs font-medium',
                !device.is_active
                  ? 'bg-red-100 text-red-800'
                  : online ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-600',
              )}
            >
              {!device.is_active ? t('device.inactive') : online ? t('device.online') : t('device.offline')}
            </span>
          </div>
          <p className="text-sm text-gray-500">
            {device.serial_number}
            {device.location_description && ` — ${device.location_description}`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link
            to={`/devices/${device.id}/config`}
            className="flex items-center gap-1 px-3 py-2 border border-gray-300 rounded-md text-sm hover:bg-gray-50"
          >
            <Settings className="h-4 w-4" /> {t('device.config')}
          </Link>
          {isAdmin && device.is_active && (
            <button
              onClick={handleDeactivate}
              className="px-3 py-2 border border-red-300 text-red-600 rounded-md text-sm hover:bg-red-50"
            >
              {t('device.deactivate')}
            </button>
          )}
          {isAdmin && !device.is_active && (
            <button
              onClick={handleActivate}
              className="px-3 py-2 border border-green-300 text-green-600 rounded-md text-sm hover:bg-green-50"
            >
              {t('device.activate')}
            </button>
          )}
        </div>
      </div>

      <div className="border-b border-gray-200 mb-6">
        <nav className="flex gap-6">
          {tabs.map((tabItem) => (
            <button
              key={tabItem.key}
              onClick={() => setTab(tabItem.key)}
              className={cn(
                'pb-3 text-sm font-medium border-b-2 transition-colors',
                tab === tabItem.key
                  ? 'border-green-500 text-green-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700',
              )}
            >
              {tabItem.label}
            </button>
          ))}
        </nav>
      </div>

      {tab === 'telemetry' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-white rounded-lg border p-4">
            <TelemetryChart readings={telemetry} dataKey="battery_soc" label={t('telemetry.battery_soc')} unit="%" />
          </div>
          <div className="bg-white rounded-lg border p-4">
            <TelemetryChart readings={telemetry} dataKey="battery_voltage" label={t('telemetry.battery_voltage')} unit="V" color="#2563eb" />
          </div>
          <div className="bg-white rounded-lg border p-4">
            <TelemetryChart readings={telemetry} dataKey="temperature" label={t('telemetry.temperature')} unit="°C" color="#dc2626" />
          </div>
          <div className="bg-white rounded-lg border p-4">
            <TelemetryChart readings={telemetry} dataKey="humidity" label={t('telemetry.humidity')} unit="%" color="#7c3aed" />
          </div>
          <div className="bg-white rounded-lg border p-4">
            <TelemetryChart readings={telemetry} dataKey="pictures_taken" label={t('telemetry.pictures_taken')} unit="" color="#f59e0b" />
          </div>
        </div>
      )}

      {tab === 'thumbnails' && (
        <div>
          {thumbnails.length === 0 ? (
            <p className="text-gray-500 text-sm">{t('device.thumbnails.empty')}</p>
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
              {thumbnails.map((thumb) => (
                <div key={thumb.id} className="bg-white rounded-lg border overflow-hidden">
                  <img
                    src={`/api/devices/${device.id}/thumbnails/${thumb.id}/image`}
                    alt={t('device.capture', { date: formatDate(thumb.timestamp) })}
                    className="w-full h-32 object-cover"
                  />
                  <div className="p-2">
                    <p className="text-xs text-gray-500">{formatDate(thumb.timestamp)}</p>
                    <p className="text-xs text-gray-400">{(thumb.file_size_bytes / 1024).toFixed(1)} KB</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
