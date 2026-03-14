export interface ConfigFieldDef {
  key: string
  type: 'number' | 'string' | 'boolean' | 'select'
  labelKey: string
  min?: number
  max?: number
  options?: string[]
}

export interface ConfigSectionDef {
  key: string
  labelKey: string
  fields: ConfigFieldDef[]
}

export const CONFIG_SECTIONS: ConfigSectionDef[] = [
  {
    key: 'camera',
    labelKey: 'config.section.camera',
    fields: [
      { key: 'resolution_width', type: 'number', labelKey: 'config.camera.resolution_width', min: 640, max: 7680 },
      { key: 'resolution_height', type: 'number', labelKey: 'config.camera.resolution_height', min: 480, max: 4320 },
      { key: 'camera_id', type: 'number', labelKey: 'config.camera.camera_id', min: 0 },
      { key: 'autofocus_mode', type: 'select', labelKey: 'config.camera.autofocus_mode', options: ['continuous', 'manual', 'fixed'] },
      { key: 'jpeg_quality', type: 'number', labelKey: 'config.camera.jpeg_quality', min: 1, max: 100 },
    ],
  },
  {
    key: 'telemetry',
    labelKey: 'config.section.telemetry',
    fields: [
      { key: 'collection_interval_minutes', type: 'number', labelKey: 'config.telemetry.collection_interval_minutes', min: 1 },
    ],
  },
  {
    key: 'upload',
    labelKey: 'config.section.upload',
    fields: [
      { key: 'interval_minutes', type: 'number', labelKey: 'config.upload.interval_minutes', min: 1 },
      { key: 'max_batch_size', type: 'number', labelKey: 'config.upload.max_batch_size', min: 1 },
      { key: 'battery_soc_threshold', type: 'number', labelKey: 'config.upload.battery_soc_threshold', min: 0, max: 100 },
    ],
  },
  {
    key: 'power',
    labelKey: 'config.section.power',
    fields: [
      { key: 'night_mode_enabled', type: 'boolean', labelKey: 'config.power.night_mode_enabled' },
      { key: 'night_start_hour', type: 'number', labelKey: 'config.power.night_start_hour', min: 0, max: 23 },
      { key: 'night_end_hour', type: 'number', labelKey: 'config.power.night_end_hour', min: 0, max: 23 },
      { key: 'modem_always_off', type: 'boolean', labelKey: 'config.power.modem_always_off' },
      { key: 'zigbee_always_on', type: 'boolean', labelKey: 'config.power.zigbee_always_on' },
      { key: 'battery', type: 'boolean', labelKey: 'config.power.battery' },
      { key: 'wlan_timeout_minutes', type: 'number', labelKey: 'config.power.wlan_timeout_minutes', min: 1 },
    ],
  },
  {
    key: 'storage',
    labelKey: 'config.section.storage',
    fields: [
      { key: 'buffer_db_path', type: 'string', labelKey: 'config.storage.buffer_db_path' },
      { key: 'backup_path', type: 'string', labelKey: 'config.storage.backup_path' },
      { key: 'backup_interval_minutes', type: 'number', labelKey: 'config.storage.backup_interval_minutes', min: 1 },
      { key: 'cleanup_after_days', type: 'number', labelKey: 'config.storage.cleanup_after_days', min: 1 },
    ],
  },
  {
    key: 'webserver',
    labelKey: 'config.section.webserver',
    fields: [
      { key: 'enabled', type: 'boolean', labelKey: 'config.webserver.enabled' },
      { key: 'host', type: 'string', labelKey: 'config.webserver.host' },
      { key: 'port', type: 'number', labelKey: 'config.webserver.port', min: 1, max: 65535 },
      { key: 'camera_fps', type: 'number', labelKey: 'config.webserver.camera_fps', min: 1, max: 30 },
      { key: 'detections_dir', type: 'string', labelKey: 'config.webserver.detections_dir' },
    ],
  },
]
