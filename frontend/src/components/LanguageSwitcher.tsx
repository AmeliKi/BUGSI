import { useTranslation } from 'react-i18next'
import { useAuth } from '../context/AuthContext'
import { cn } from '../lib/utils'

const LANGUAGES = [
  { code: 'en', label: 'EN' },
  { code: 'de', label: 'DE' },
] as const

export default function LanguageSwitcher() {
  const { i18n } = useTranslation()
  const { setLanguage } = useAuth()

  return (
    <div className="flex gap-1">
      {LANGUAGES.map((lang) => (
        <button
          key={lang.code}
          onClick={() => setLanguage(lang.code)}
          className={cn(
            'px-2 py-1 rounded text-xs font-medium transition-colors',
            i18n.language === lang.code
              ? 'bg-green-100 text-green-700'
              : 'text-gray-500 hover:bg-gray-100',
          )}
        >
          {lang.label}
        </button>
      ))}
    </div>
  )
}
