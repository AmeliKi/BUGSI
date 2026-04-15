// @vitest-environment node
import { describe, expect, it } from 'vitest'
import { TELEMETRY_SECTIONS } from '../../src/components/devices/TelemetrySectionGroup'
import type { TelemetryReading } from '../../src/api/devices'

describe('TELEMETRY_SECTIONS', () => {
  it('contains 5 sections', () => {
    expect(TELEMETRY_SECTIONS.length).toBe(5)
  })

  it('contains 15 charts total', () => {
    const total = TELEMETRY_SECTIONS.reduce((sum, s) => sum + s.charts.length, 0)
    expect(total).toBe(15)
  })

  it('has unique dataKeys across all charts', () => {
    const keys = TELEMETRY_SECTIONS.flatMap((s) => s.charts.map((c) => c.dataKey))
    expect(new Set(keys).size).toBe(keys.length)
  })

  it('all dataKeys are valid TelemetryReading fields', () => {
    const validKeys: (keyof TelemetryReading)[] = [
      'battery_voltage', 'battery_soc', 'battery_current', 'battery_power',
      'battery_consumed_ah', 'battery_ttg_min', 'temperature', 'humidity',
      'lte_signal_strength', 'lte_signal_quality', 'storage_used_mb',
      'storage_total_mb', 'cpu_temp', 'uptime_seconds', 'pictures_taken',
    ]
    const keys = TELEMETRY_SECTIONS.flatMap((s) => s.charts.map((c) => c.dataKey))
    for (const key of keys) {
      expect(validKeys).toContain(key)
    }
  })

  it('has correct section order', () => {
    const titleKeys = TELEMETRY_SECTIONS.map((s) => s.titleKey)
    expect(titleKeys).toEqual([
      'telemetry.section.battery',
      'telemetry.section.environment',
      'telemetry.section.connectivity',
      'telemetry.section.system',
      'telemetry.section.activity',
    ])
  })

  it('battery section has 6 charts', () => {
    const battery = TELEMETRY_SECTIONS.find((s) => s.titleKey === 'telemetry.section.battery')!
    expect(battery.charts.length).toBe(6)
  })

  it('all charts have a color', () => {
    const charts = TELEMETRY_SECTIONS.flatMap((s) => s.charts)
    for (const chart of charts) {
      expect(chart.color).toMatch(/^#[0-9a-f]{6}$/i)
    }
  })

  it('all charts have unique colors', () => {
    const colors = TELEMETRY_SECTIONS.flatMap((s) => s.charts.map((c) => c.color))
    expect(new Set(colors).size).toBe(colors.length)
  })
})

describe('visibility filtering logic', () => {
  const allFields = TELEMETRY_SECTIONS.flatMap((s) => s.charts.map((c) => c.dataKey))

  it('no hidden fields means all charts visible', () => {
    const hiddenFields: string[] = []
    for (const section of TELEMETRY_SECTIONS) {
      const visible = section.charts.filter((c) => !hiddenFields.includes(c.dataKey))
      expect(visible.length).toBe(section.charts.length)
    }
  })

  it('hiding all fields results in no visible charts', () => {
    const hiddenFields = [...allFields]
    for (const section of TELEMETRY_SECTIONS) {
      const visible = section.charts.filter((c) => !hiddenFields.includes(c.dataKey))
      expect(visible.length).toBe(0)
    }
  })

  it('hiding specific fields filters correctly', () => {
    const hiddenFields = ['battery_soc', 'temperature', 'cpu_temp']
    const battery = TELEMETRY_SECTIONS.find((s) => s.titleKey === 'telemetry.section.battery')!
    const visible = battery.charts.filter((c) => !hiddenFields.includes(c.dataKey))
    expect(visible.length).toBe(5) // 6 minus battery_soc
  })

  it('section with all charts hidden is empty', () => {
    const hiddenFields = ['lte_signal_strength', 'lte_signal_quality']
    const connectivity = TELEMETRY_SECTIONS.find((s) => s.titleKey === 'telemetry.section.connectivity')!
    const visible = connectivity.charts.filter((c) => !hiddenFields.includes(c.dataKey))
    expect(visible.length).toBe(0)
  })
})
