import { useTranslation } from 'react-i18next'
import type { ConfigFieldDef } from './configSchema'

interface ConfigFieldProps {
  field: ConfigFieldDef
  value: unknown
  defaultValue?: unknown
  onChange: (key: string, value: unknown) => void
}

export default function ConfigField({ field, value, defaultValue, onChange }: ConfigFieldProps) {
  const { t } = useTranslation()

  if (field.type === 'boolean') {
    return (
      <label className="flex items-center justify-between py-2">
        <span className="text-sm text-gray-700">{t(field.labelKey)}</span>
        <button
          type="button"
          role="switch"
          aria-checked={!!value}
          onClick={() => onChange(field.key, !value)}
          className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors ${
            value ? 'bg-green-600' : 'bg-gray-200'
          }`}
        >
          <span
            className={`pointer-events-none inline-block h-5 w-5 rounded-full bg-white shadow transform transition-transform ${
              value ? 'translate-x-5' : 'translate-x-0'
            }`}
          />
        </button>
      </label>
    )
  }

  if (field.type === 'select') {
    return (
      <label className="flex items-center justify-between py-2">
        <span className="text-sm text-gray-700">{t(field.labelKey)}</span>
        <select
          value={String(value ?? '')}
          onChange={(e) => onChange(field.key, e.target.value)}
          className="w-48 rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
        >
          {field.options?.map((opt) => (
            <option key={opt} value={opt}>{opt}</option>
          ))}
        </select>
      </label>
    )
  }

  if (field.type === 'number') {
    return (
      <label className="flex items-center justify-between py-2">
        <span className="text-sm text-gray-700">{t(field.labelKey)}</span>
        <input
          type="number"
          value={value != null ? String(value) : ''}
          min={field.min}
          max={field.max}
          placeholder={defaultValue != null ? String(defaultValue) : ''}
          onChange={(e) => onChange(field.key, e.target.value === '' ? null : Number(e.target.value))}
          className="w-48 rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
        />
      </label>
    )
  }

  // string
  return (
    <label className="flex items-center justify-between py-2">
      <span className="text-sm text-gray-700">{t(field.labelKey)}</span>
      <input
        type="text"
        value={String(value ?? '')}
        placeholder={defaultValue != null ? String(defaultValue) : ''}
        onChange={(e) => onChange(field.key, e.target.value)}
        className="w-48 rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
      />
    </label>
  )
}
