import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import type { Device } from '../../api/devices'
import { cn, isOnline, timeAgo } from '../../lib/utils'

interface DeviceCardProps {
  device: Device
}

export default function DeviceCard({ device }: DeviceCardProps) {
  const { t } = useTranslation()
  const online = isOnline(device.last_seen_at)

  return (
    <Link
      to={`/devices/${device.id}`}
      className="block bg-white rounded-lg border border-gray-200 p-4 hover:shadow-md transition-shadow"
    >
      <div className="flex items-start justify-between mb-3">
        <div>
          <h3 className="font-medium text-gray-900">{device.name}</h3>
          <p className="text-xs text-gray-500">{device.serial_number}</p>
        </div>
        <span
          className={cn(
            'inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium',
            !device.is_active
              ? 'bg-red-100 text-red-800'
              : online ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-600',
          )}
        >
          {!device.is_active ? t('device.inactive') : online ? t('device.online') : t('device.offline')}
        </span>
      </div>

      {device.location_description && (
        <p className="text-xs text-gray-500 mb-3">{device.location_description}</p>
      )}

      {(device.has_config_pending || device.has_ota_pending) && (
        <div className="flex gap-2 mb-3">
          {device.has_config_pending && (
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">
              {t('device.config_pending')}
            </span>
          )}
          {device.has_ota_pending && (
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
              {t('device.ota_pending')}
            </span>
          )}
        </div>
      )}

      <div className="text-xs text-gray-500">
        {device.last_seen_at ? t('device.last_seen', { time: timeAgo(device.last_seen_at) }) : t('device.never_connected')}
      </div>
    </Link>
  )
}
