import { ChevronDown, ChevronRight, RotateCcw } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import ConfigField from './ConfigField'
import type { ConfigSectionDef } from './configSchema'

interface ConfigSectionProps {
  section: ConfigSectionDef
  values: Record<string, unknown>
  defaults?: Record<string, unknown>
  onChange: (sectionKey: string, fieldKey: string, value: unknown) => void
  onResetSection: (sectionKey: string) => void
}

export default function ConfigSection({ section, values, defaults, onChange, onResetSection }: ConfigSectionProps) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(true)

  return (
    <div className="border rounded-lg bg-white mb-3">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-gray-50"
      >
        <div className="flex items-center gap-2">
          {open ? <ChevronDown className="h-4 w-4 text-gray-400" /> : <ChevronRight className="h-4 w-4 text-gray-400" />}
          <span className="font-medium text-gray-900">{t(section.labelKey)}</span>
        </div>
      </button>

      {open && (
        <div className="px-4 pb-4 border-t">
          <div className="divide-y divide-gray-100">
            {section.fields.map((field) => (
              <ConfigField
                key={field.key}
                field={field}
                value={values[field.key]}
                defaultValue={defaults?.[field.key]}
                onChange={(key, val) => onChange(section.key, key, val)}
              />
            ))}
          </div>
          <div className="mt-3 pt-3 border-t">
            <button
              type="button"
              onClick={() => {
                if (window.confirm(t('config.reset_confirm'))) {
                  onResetSection(section.key)
                }
              }}
              className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700"
            >
              <RotateCcw className="h-3 w-3" />
              {t('config.reset_section')}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
