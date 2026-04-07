import { ArrowLeft, Eye, EyeOff, Settings } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useParams } from 'react-router-dom'
import type { Device, TelemetryReading, Thumbnail } from '../api/devices'
import { activateDevice, deactivateDevice, getDevice, getTelemetry, getThumbnails } from '../api/devices'
import TelemetrySectionGroup, { TELEMETRY_SECTIONS } from '../components/devices/TelemetrySectionGroup'
import { useAuth } from '../context/AuthContext'
import { cn, formatDate, isOnline } from '../lib/utils'

type Tab = 'telemetry' | 'thumbnails'

const ALL_TELEMETRY_FIELDS = TELEMETRY_SECTIONS.flatMap((s) => s.charts.map((c) => c.dataKey))

export default function DeviceDetailPage() {
  const { t } = useTranslation()
  const { user, isAdmin, updatePreferences } = useAuth()
  const navigate = useNavigate()
  const { deviceId } = useParams<{ deviceId: string }>()
  const [device, setDevice] = useState<Device | null>(null)
  const [tab, setTab] = useState<Tab>('telemetry')
  const [telemetry, setTelemetry] = useState<TelemetryReading[]>([])
  const [thumbnails, setThumbnails] = useState<Thumbnail[]>([])
  const [showVisibilityMenu, setShowVisibilityMenu] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  const hiddenFields = ((user?.preferences as Record<string, unknown>)?.hidden_telemetry_fields as string[]) ?? []

  useEffect(() => {
    if (!deviceId) return
    getDevice(deviceId).then(({ data }) => setDevice(data))
    getTelemetry(deviceId, { limit: 100 }).then(({ data }) => setTelemetry(data))
    getThumbnails(deviceId, { limit: 30 }).then(({ data }) => setThumbnails(data))
  }, [deviceId])

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setShowVisibilityMenu(false)
      }
    }
    if (showVisibilityMenu) document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [showVisibilityMenu])

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

  const toggleField = async (field: string) => {
    const newHidden = hiddenFields.includes(field)
      ? hiddenFields.filter((f) => f !== field)
      : [...hiddenFields, field]
    await updatePreferences({ hidden_telemetry_fields: newHidden })
  }

  const showAll = async () => {
    await updatePreferences({ hidden_telemetry_fields: [] })
  }

  const hideAll = async () => {
    await updatePreferences({ hidden_telemetry_fields: [...ALL_TELEMETRY_FIELDS] })
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
        <nav className="flex gap-6 items-center">
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
          {tab === 'telemetry' && (
            <div className="relative ml-auto pb-3" ref={menuRef}>
              <button
                onClick={() => setShowVisibilityMenu(!showVisibilityMenu)}
                className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700"
                title={t('telemetry.visibility')}
              >
                {hiddenFields.length > 0 ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                <span className="hidden sm:inline">{t('telemetry.visibility')}</span>
              </button>
              {showVisibilityMenu && (
                <div className="absolute right-0 top-full mt-1 w-64 bg-white rounded-lg border shadow-lg z-10 p-3">
                  <p className="text-xs text-gray-500 mb-2">{t('telemetry.visibility.description')}</p>
                  <div className="flex gap-2 mb-2">
                    <button onClick={showAll} className="text-xs text-green-600 hover:underline">{t('telemetry.visibility.show_all')}</button>
                    <button onClick={hideAll} className="text-xs text-gray-500 hover:underline">{t('telemetry.visibility.hide_all')}</button>
                  </div>
                  <div className="space-y-1 max-h-64 overflow-y-auto">
                    {TELEMETRY_SECTIONS.map((section) => (
                      <div key={section.titleKey}>
                        <p className="text-xs font-semibold text-gray-600 mt-2 mb-1">{t(section.titleKey)}</p>
                        {section.charts.map((chart) => (
                          <label key={chart.dataKey} className="flex items-center gap-2 py-0.5 cursor-pointer">
                            <input
                              type="checkbox"
                              checked={!hiddenFields.includes(chart.dataKey)}
                              onChange={() => toggleField(chart.dataKey)}
                              className="rounded border-gray-300 text-green-600 focus:ring-green-500"
                            />
                            <span className="text-sm text-gray-700">{t(chart.labelKey)}</span>
                          </label>
                        ))}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </nav>
      </div>

      {tab === 'telemetry' && (
        <div className="space-y-8">
          {TELEMETRY_SECTIONS.map((section) => (
            <TelemetrySectionGroup
              key={section.titleKey}
              section={section}
              readings={telemetry}
              hiddenFields={hiddenFields}
            />
          ))}
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
