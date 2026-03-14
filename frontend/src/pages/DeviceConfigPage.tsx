import { ArrowLeft, Check, Code, List, RefreshCw } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router-dom'
import type { DeviceConfig } from '../api/devices'
import { getConfig, getDefaultConfig, updateConfig } from '../api/devices'
import ConfigSection from '../components/config/ConfigSection'
import { CONFIG_SECTIONS } from '../components/config/configSchema'

type ViewMode = 'form' | 'json'

export default function DeviceConfigPage() {
  const { t } = useTranslation()
  const { deviceId } = useParams<{ deviceId: string }>()
  const [config, setConfig] = useState<DeviceConfig | null>(null)
  const [defaults, setDefaults] = useState<Record<string, unknown>>({})
  const [formValues, setFormValues] = useState<Record<string, Record<string, unknown>>>({})
  const [json, setJson] = useState('')
  const [viewMode, setViewMode] = useState<ViewMode>('form')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!deviceId) return
    Promise.all([
      getConfig(deviceId),
      getDefaultConfig(),
    ]).then(([configRes, defaultsRes]) => {
      setConfig(configRes.data)
      setDefaults(defaultsRes.data)
      setJson(JSON.stringify(configRes.data.config_json, null, 2))
      setFormValues(configRes.data.config_json as Record<string, Record<string, unknown>>)
    })
  }, [deviceId])

  const handleFieldChange = (sectionKey: string, fieldKey: string, value: unknown) => {
    setFormValues((prev) => ({
      ...prev,
      [sectionKey]: {
        ...prev[sectionKey],
        [fieldKey]: value,
      },
    }))
  }

  const handleResetSection = (sectionKey: string) => {
    const sectionDefaults = defaults[sectionKey]
    if (sectionDefaults && typeof sectionDefaults === 'object') {
      setFormValues((prev) => ({
        ...prev,
        [sectionKey]: { ...(sectionDefaults as Record<string, unknown>) },
      }))
    }
  }

  const handleSave = async () => {
    if (!deviceId) return
    setError('')
    setSaving(true)
    try {
      let configToSave: Record<string, unknown>
      if (viewMode === 'json') {
        configToSave = JSON.parse(json)
      } else {
        configToSave = { ...formValues }
      }
      const { data } = await updateConfig(deviceId, configToSave)
      setConfig(data)
      setFormValues(data.config_json as Record<string, Record<string, unknown>>)
      setJson(JSON.stringify(data.config_json, null, 2))
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (err) {
      setError(err instanceof Error ? err.message : t('config.error_fallback'))
    } finally {
      setSaving(false)
    }
  }

  const switchView = (mode: ViewMode) => {
    if (mode === 'json' && viewMode === 'form') {
      setJson(JSON.stringify(formValues, null, 2))
    } else if (mode === 'form' && viewMode === 'json') {
      try {
        setFormValues(JSON.parse(json))
      } catch {
        // keep current form values if JSON is invalid
      }
    }
    setViewMode(mode)
  }

  if (!config) return <p className="text-gray-500">{t('device.loading')}</p>

  const synced = config.version === config.last_acked_version

  return (
    <div>
      <div className="flex items-center gap-3 mb-6">
        <Link to={`/devices/${deviceId}`} className="text-gray-400 hover:text-gray-600">
          <ArrowLeft className="h-5 w-5" />
        </Link>
        <h1 className="text-2xl font-bold text-gray-900">{t('config.title')}</h1>
      </div>

      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-4 text-sm">
          <span className="text-gray-500">{t('config.version')} <strong>{config.version}</strong></span>
          <span className={synced ? 'text-green-600' : 'text-yellow-600'}>
            {synced ? (
              <span className="flex items-center gap-1"><Check className="h-3 w-3" /> {t('config.synced')}</span>
            ) : (
              <span className="flex items-center gap-1"><RefreshCw className="h-3 w-3" /> {t('config.pending_sync', { version: config.last_acked_version })}</span>
            )}
          </span>
        </div>

        <div className="flex rounded-md border border-gray-300 overflow-hidden">
          <button
            type="button"
            onClick={() => switchView('form')}
            className={`flex items-center gap-1 px-3 py-1.5 text-sm ${viewMode === 'form' ? 'bg-green-600 text-white' : 'bg-white text-gray-700 hover:bg-gray-50'}`}
          >
            <List className="h-3.5 w-3.5" />
            {t('config.view_form')}
          </button>
          <button
            type="button"
            onClick={() => switchView('json')}
            className={`flex items-center gap-1 px-3 py-1.5 text-sm border-l ${viewMode === 'json' ? 'bg-green-600 text-white' : 'bg-white text-gray-700 hover:bg-gray-50'}`}
          >
            <Code className="h-3.5 w-3.5" />
            JSON
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 text-red-700 text-sm p-3 rounded-md mb-4">{error}</div>
      )}

      {viewMode === 'form' ? (
        <div>
          {CONFIG_SECTIONS.map((section) => (
            <ConfigSection
              key={section.key}
              section={section}
              values={(formValues[section.key] as Record<string, unknown>) ?? {}}
              defaults={(defaults[section.key] as Record<string, unknown>) ?? {}}
              onChange={handleFieldChange}
              onResetSection={handleResetSection}
            />
          ))}
        </div>
      ) : (
        <div className="bg-white rounded-lg border">
          <textarea
            value={json}
            onChange={(e) => setJson(e.target.value)}
            rows={20}
            className="w-full p-4 font-mono text-sm border-none rounded-lg focus:outline-none focus:ring-2 focus:ring-green-500"
            spellCheck={false}
          />
        </div>
      )}

      <div className="mt-4 flex gap-2">
        <button
          onClick={handleSave}
          disabled={saving}
          className="bg-green-600 text-white px-4 py-2 rounded-md text-sm hover:bg-green-700 disabled:opacity-50"
        >
          {saving ? t('config.saving') : saved ? t('config.saved') : t('config.save')}
        </button>
      </div>
    </div>
  )
}
