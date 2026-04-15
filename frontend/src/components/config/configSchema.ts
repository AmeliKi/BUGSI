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
    key: 'still_camera',
    labelKey: 'config.section.still_camera',
    fields: [
      { key: 'type', type: 'select', labelKey: 'config.still_camera.type', options: ['arducam_64mp', 'ids_rgb'] },
      { key: 'resolution_width', type: 'number', labelKey: 'config.still_camera.resolution_width', min: 640, max: 7680 },
      { key: 'resolution_height', type: 'number', labelKey: 'config.still_camera.resolution_height', min: 480, max: 4320 },
      { key: 'camera_id', type: 'number', labelKey: 'config.still_camera.camera_id', min: 0 },
      { key: 'autofocus_mode', type: 'select', labelKey: 'config.still_camera.autofocus_mode', options: ['continuous', 'manual', 'fixed'] },
      { key: 'jpeg_quality', type: 'number', labelKey: 'config.still_camera.jpeg_quality', min: 1, max: 100 },
      { key: 'exposure_us', type: 'number', labelKey: 'config.still_camera.exposure_us', min: 0 },
      { key: 'gain_db', type: 'number', labelKey: 'config.still_camera.gain_db', min: 0 },
      { key: 'white_balance', type: 'select', labelKey: 'config.still_camera.white_balance', options: ['auto', 'once', 'off'] },
      { key: 'balance_ratio_red', type: 'number', labelKey: 'config.still_camera.balance_ratio_red', min: 0 },
      { key: 'balance_ratio_green', type: 'number', labelKey: 'config.still_camera.balance_ratio_green', min: 0 },
      { key: 'balance_ratio_blue', type: 'number', labelKey: 'config.still_camera.balance_ratio_blue', min: 0 },
      { key: 'gamma', type: 'number', labelKey: 'config.still_camera.gamma', min: 0, max: 4 },
      { key: 'black_level', type: 'number', labelKey: 'config.still_camera.black_level', min: 0 },
      { key: 'acquisition_frame_rate', type: 'number', labelKey: 'config.still_camera.acquisition_frame_rate', min: 0, max: 30 },
      { key: 'binning_horizontal', type: 'number', labelKey: 'config.still_camera.binning_horizontal', min: 1, max: 4 },
      { key: 'binning_vertical', type: 'number', labelKey: 'config.still_camera.binning_vertical', min: 1, max: 4 },
    ],
  },
  {
    key: 'event_camera',
    labelKey: 'config.section.event_camera',
    fields: [
      { key: 'type', type: 'select', labelKey: 'config.event_camera.type', options: ['prophesee_genx320', 'ids_evs'] },
      { key: 'device_path', type: 'string', labelKey: 'config.event_camera.device_path' },
      { key: 'event_threshold', type: 'number', labelKey: 'config.event_camera.event_threshold', min: 1 },
      { key: 'detection_window_ms', type: 'number', labelKey: 'config.event_camera.detection_window_ms', min: 1 },
      { key: 'min_cluster_area', type: 'number', labelKey: 'config.event_camera.min_cluster_area', min: 1 },
      { key: 'jpeg_quality', type: 'number', labelKey: 'config.event_camera.jpeg_quality', min: 1, max: 100 },
      { key: 'bias_diff_on', type: 'number', labelKey: 'config.event_camera.bias_diff_on', min: 0 },
      { key: 'bias_diff_off', type: 'number', labelKey: 'config.event_camera.bias_diff_off', min: 0 },
      { key: 'bias_fo', type: 'number', labelKey: 'config.event_camera.bias_fo', min: 0 },
      { key: 'bias_hpf', type: 'number', labelKey: 'config.event_camera.bias_hpf', min: 0 },
      { key: 'bias_refr', type: 'number', labelKey: 'config.event_camera.bias_refr', min: 0 },
    ],
  },
  {
    key: 'image_capture',
    labelKey: 'config.section.image_capture',
    fields: [
      { key: 'enabled', type: 'boolean', labelKey: 'config.image_capture.enabled' },
      { key: 'cooldown_seconds', type: 'number', labelKey: 'config.image_capture.cooldown_seconds', min: 0 },
      { key: 'zigbee_warmup_seconds', type: 'number', labelKey: 'config.image_capture.zigbee_warmup_seconds', min: 0 },
      { key: 'thumbnail_width', type: 'number', labelKey: 'config.image_capture.thumbnail_width', min: 1 },
      { key: 'thumbnail_height', type: 'number', labelKey: 'config.image_capture.thumbnail_height', min: 1 },
      { key: 'save_full_resolution', type: 'boolean', labelKey: 'config.image_capture.save_full_resolution' },
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
      { key: 'night_mode_type', type: 'select', labelKey: 'config.power.night_mode_type', options: ['fixed', 'location-based'] },
      { key: 'awake_start_hour', type: 'number', labelKey: 'config.power.awake_start_hour', min: 0, max: 23 },
      { key: 'awake_end_hour', type: 'number', labelKey: 'config.power.awake_end_hour', min: 0, max: 23 },
      { key: 'modem_always_off', type: 'boolean', labelKey: 'config.power.modem_always_off' },
      { key: 'battery', type: 'boolean', labelKey: 'config.power.battery' },
      { key: 'wlan_timeout_minutes', type: 'number', labelKey: 'config.power.wlan_timeout_minutes', min: 1 },
      { key: 'energy_saving', type: 'boolean', labelKey: 'config.power.energy_saving' },
      { key: 'energy_saving_wlan_minutes', type: 'number', labelKey: 'config.power.energy_saving_wlan_minutes', min: 1 },
    ],
  },
  {
    key: 'lte',
    labelKey: 'config.section.lte',
    fields: [
      { key: 'gpio_pin', type: 'number', labelKey: 'config.lte.gpio_pin', min: 0 },
    ],
  },
  {
    key: 'zigbee',
    labelKey: 'config.section.zigbee',
    fields: [
      { key: 'serial_port', type: 'string', labelKey: 'config.zigbee.serial_port' },
      { key: 'adapter', type: 'select', labelKey: 'config.zigbee.adapter', options: ['ezsp', 'znp', 'deconz'] },
      { key: 'device_name', type: 'string', labelKey: 'config.zigbee.device_name' },
      { key: 'network_channel', type: 'number', labelKey: 'config.zigbee.network_channel', min: 11, max: 26 },
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
