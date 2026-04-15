import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { changeMyPassword } from '../api/auth'
import { TELEMETRY_SECTIONS } from '../components/devices/TelemetrySectionGroup'
import { useAuth } from '../context/AuthContext'

export default function SettingsPage() {
  const { t } = useTranslation()
  const { user, updatePreferences } = useAuth()
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  const hiddenFields = ((user?.preferences as Record<string, unknown>)?.hidden_telemetry_fields as string[]) ?? []

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setSuccess(false)

    if (newPassword !== confirmPassword) {
      setError(t('settings.password.mismatch'))
      return
    }

    setSubmitting(true)
    try {
      await changeMyPassword(currentPassword, newPassword)
      setSuccess(true)
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
    } catch (err) {
      setError(err instanceof Error ? err.message : t('settings.password.error_fallback'))
    } finally {
      setSubmitting(false)
    }
  }

  const toggleField = async (field: string) => {
    const newHidden = hiddenFields.includes(field)
      ? hiddenFields.filter((f) => f !== field)
      : [...hiddenFields, field]
    await updatePreferences({ hidden_telemetry_fields: newHidden })
  }

  const showAll = () => updatePreferences({ hidden_telemetry_fields: [] })
  const hideAll = () => {
    const allFields = TELEMETRY_SECTIONS.flatMap((s) => s.charts.map((c) => c.dataKey))
    return updatePreferences({ hidden_telemetry_fields: allFields })
  }

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 mb-6">{t('settings.title')}</h1>

      <div className="bg-white rounded-lg border p-6 max-w-md mb-6">
        <h2 className="text-lg font-semibold text-gray-800 mb-4">{t('settings.password.title')}</h2>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">{t('settings.password.current')}</label>
            <input
              type="password"
              required
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              className="w-full px-3 py-2 border rounded-md text-sm"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">{t('settings.password.new')}</label>
            <input
              type="password"
              required
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              className="w-full px-3 py-2 border rounded-md text-sm"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">{t('settings.password.confirm')}</label>
            <input
              type="password"
              required
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className="w-full px-3 py-2 border rounded-md text-sm"
            />
          </div>

          {error && <p className="text-sm text-red-600">{error}</p>}
          {success && <p className="text-sm text-green-600">{t('settings.password.success')}</p>}

          <button
            type="submit"
            disabled={submitting}
            className="bg-green-600 text-white px-4 py-2 rounded-md text-sm hover:bg-green-700 disabled:opacity-50"
          >
            {submitting ? t('settings.password.submitting') : t('settings.password.submit')}
          </button>
        </form>
      </div>

      <div className="bg-white rounded-lg border p-6 max-w-md">
        <h2 className="text-lg font-semibold text-gray-800 mb-2">{t('settings.telemetry.title')}</h2>
        <p className="text-sm text-gray-500 mb-4">{t('settings.telemetry.description')}</p>

        <div className="flex gap-3 mb-3">
          <button onClick={showAll} className="text-sm text-green-600 hover:underline">{t('telemetry.visibility.show_all')}</button>
          <button onClick={hideAll} className="text-sm text-gray-500 hover:underline">{t('telemetry.visibility.hide_all')}</button>
        </div>

        <div className="space-y-1">
          {TELEMETRY_SECTIONS.map((section) => (
            <div key={section.titleKey}>
              <p className="text-xs font-semibold text-gray-600 mt-3 mb-1">{t(section.titleKey)}</p>
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
    </div>
  )
}
