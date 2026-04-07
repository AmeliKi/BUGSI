import { apiFetch } from './client'

export interface Device {
  id: string
  name: string
  serial_number: string
  api_key_prefix: string
  location_lat: number | null
  location_lon: number | null
  location_description: string | null
  firmware_version: string | null
  last_seen_at: string | null
  is_active: boolean
  created_at: string
  updated_at: string
  has_config_pending: boolean
  has_ota_pending: boolean
}

export interface DeviceCreateResponse extends Device {
  api_key: string
}

export interface TelemetryReading {
  id: string
  device_id: string
  timestamp: string
  battery_voltage: number | null
  battery_soc: number | null
  battery_current: number | null
  battery_power: number | null
  battery_consumed_ah: number | null
  battery_ttg_min: number | null
  temperature: number | null
  humidity: number | null
  lte_signal_strength: number | null
  lte_signal_quality: number | null
  storage_used_mb: number | null
  storage_total_mb: number | null
  cpu_temp: number | null
  uptime_seconds: number | null
  pictures_taken: number | null
  created_at: string
}

export interface Thumbnail {
  id: string
  device_id: string
  timestamp: string
  file_path: string
  file_size_bytes: number
  created_at: string
}

export interface DeviceConfig {
  id: string
  device_id: string
  config_json: Record<string, unknown>
  version: number
  last_acked_version: number
  updated_by: string | null
  created_at: string
  updated_at: string
}

export async function listDevices(offset = 0, limit = 50, includeInactive = true) {
  return apiFetch<Device[]>(`/devices?offset=${offset}&limit=${limit}&include_inactive=${includeInactive}`)
}

export async function getDevice(id: string) {
  return apiFetch<Device>(`/devices/${id}`)
}

export async function createDevice(data: { name: string; serial_number: string; location_lat?: number; location_lon?: number; location_description?: string }) {
  return apiFetch<DeviceCreateResponse>('/devices', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function getTelemetry(deviceId: string, params?: { from?: string; to?: string; limit?: number }) {
  const qs = new URLSearchParams()
  if (params?.from) qs.set('from_ts', params.from)
  if (params?.to) qs.set('to_ts', params.to)
  if (params?.limit) qs.set('limit', String(params.limit))
  return apiFetch<TelemetryReading[]>(`/devices/${deviceId}/telemetry?${qs}`)
}

export async function getThumbnails(deviceId: string, params?: { from?: string; to?: string; limit?: number }) {
  const qs = new URLSearchParams()
  if (params?.from) qs.set('from_ts', params.from)
  if (params?.to) qs.set('to_ts', params.to)
  if (params?.limit) qs.set('limit', String(params.limit))
  return apiFetch<Thumbnail[]>(`/devices/${deviceId}/thumbnails?${qs}`)
}

export async function getConfig(deviceId: string) {
  return apiFetch<DeviceConfig>(`/config/${deviceId}`)
}

export async function deactivateDevice(id: string) {
  return apiFetch<Device>(`/devices/${id}`, { method: 'DELETE' })
}

export async function activateDevice(id: string) {
  return apiFetch<Device>(`/devices/${id}/activate`, { method: 'POST' })
}

export async function updateConfig(deviceId: string, config_json: Record<string, unknown>) {
  return apiFetch<DeviceConfig>(`/config/${deviceId}`, {
    method: 'PUT',
    body: JSON.stringify({ config_json }),
  })
}

export async function getDefaultConfig() {
  return apiFetch<Record<string, unknown>>('/config/defaults')
}
