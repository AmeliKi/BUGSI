import { useTranslation } from 'react-i18next'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { TelemetryReading } from '../../api/devices'

interface TelemetryChartProps {
  readings: TelemetryReading[]
  dataKey: keyof TelemetryReading
  label: string
  unit: string
  color?: string
}

export default function TelemetryChart({
  readings,
  dataKey,
  label,
  unit,
  color = '#16a34a',
}: TelemetryChartProps) {
  const { t } = useTranslation()
  const data = [...readings]
    .reverse()
    .map((r) => ({
      time: new Date(r.timestamp).toLocaleTimeString(),
      value: r[dataKey] as number | null,
    }))
    .filter((d) => d.value !== null)

  if (data.length === 0) {
    return (
      <div className="h-48 flex items-center justify-center text-gray-400 text-sm">
        {t('telemetry.no_data', { label: label.toLowerCase() })}
      </div>
    )
  }

  return (
    <div>
      <h4 className="text-sm font-medium text-gray-700 mb-2">
        {label}{unit ? ` (${unit})` : ''}
      </h4>
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis dataKey="time" tick={{ fontSize: 10 }} />
          <YAxis tick={{ fontSize: 10 }} />
          <Tooltip />
          <Line type="monotone" dataKey="value" stroke={color} dot={false} strokeWidth={2} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
