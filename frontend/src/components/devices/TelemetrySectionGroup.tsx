import { useTranslation } from 'react-i18next'
import type { TelemetryReading } from '../../api/devices'
import TelemetryChart from './TelemetryChart'

export interface TelemetryChartDef {
  dataKey: keyof TelemetryReading
  labelKey: string
  unit: string
  color: string
}

export interface TelemetrySectionDef {
  titleKey: string
  charts: TelemetryChartDef[]
}

interface TelemetrySectionGroupProps {
  section: TelemetrySectionDef
  readings: TelemetryReading[]
  hiddenFields?: string[]
}

export const TELEMETRY_SECTIONS: TelemetrySectionDef[] = [
  {
    titleKey: 'telemetry.section.battery',
    charts: [
      { dataKey: 'battery_soc', labelKey: 'telemetry.battery_soc', unit: '%', color: '#16a34a' },
      { dataKey: 'battery_voltage', labelKey: 'telemetry.battery_voltage', unit: 'V', color: '#2563eb' },
      { dataKey: 'battery_current', labelKey: 'telemetry.battery_current', unit: 'A', color: '#0891b2' },
      { dataKey: 'battery_power', labelKey: 'telemetry.battery_power', unit: 'W', color: '#4f46e5' },
      { dataKey: 'battery_consumed_ah', labelKey: 'telemetry.battery_consumed_ah', unit: 'Ah', color: '#9333ea' },
      { dataKey: 'battery_ttg_min', labelKey: 'telemetry.battery_ttg_min', unit: 'min', color: '#0d9488' },
    ],
  },
  {
    titleKey: 'telemetry.section.environment',
    charts: [
      { dataKey: 'temperature', labelKey: 'telemetry.temperature', unit: '°C', color: '#dc2626' },
      { dataKey: 'humidity', labelKey: 'telemetry.humidity', unit: '%', color: '#7c3aed' },
    ],
  },
  {
    titleKey: 'telemetry.section.connectivity',
    charts: [
      { dataKey: 'lte_signal_strength', labelKey: 'telemetry.lte_signal_strength', unit: 'dBm', color: '#ea580c' },
      { dataKey: 'lte_signal_quality', labelKey: 'telemetry.lte_signal_quality', unit: 'dB', color: '#d97706' },
    ],
  },
  {
    titleKey: 'telemetry.section.system',
    charts: [
      { dataKey: 'cpu_temp', labelKey: 'telemetry.cpu_temp', unit: '°C', color: '#e11d48' },
      { dataKey: 'uptime_seconds', labelKey: 'telemetry.uptime_seconds', unit: 's', color: '#475569' },
      { dataKey: 'storage_used_mb', labelKey: 'telemetry.storage_used_mb', unit: 'MB', color: '#0284c7' },
      { dataKey: 'storage_total_mb', labelKey: 'telemetry.storage_total_mb', unit: 'MB', color: '#6366f1' },
    ],
  },
  {
    titleKey: 'telemetry.section.activity',
    charts: [
      { dataKey: 'pictures_taken', labelKey: 'telemetry.pictures_taken', unit: '', color: '#f59e0b' },
    ],
  },
]

export default function TelemetrySectionGroup({ section, readings, hiddenFields = [] }: TelemetrySectionGroupProps) {
  const { t } = useTranslation()
  const visibleCharts = section.charts.filter((c) => !hiddenFields.includes(c.dataKey))
  if (visibleCharts.length === 0) return null

  return (
    <div>
      <h3 className="text-lg font-semibold text-gray-800 mb-4">{t(section.titleKey)}</h3>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {visibleCharts.map((chart) => (
          <div key={chart.dataKey} className="bg-white rounded-lg border p-4">
            <TelemetryChart
              readings={readings}
              dataKey={chart.dataKey}
              label={t(chart.labelKey)}
              unit={chart.unit}
              color={chart.color}
            />
          </div>
        ))}
      </div>
    </div>
  )
}
