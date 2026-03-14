// @vitest-environment node
import { describe, expect, it } from 'vitest'
import { cn, isOnline, timeAgo } from '../../src/lib/utils'

describe('cn', () => {
  it('merges class names', () => {
    expect(cn('foo', 'bar')).toBe('foo bar')
  })

  it('handles conditional classes', () => {
    expect(cn('base', false && 'hidden', 'visible')).toBe('base visible')
  })

  it('merges tailwind classes', () => {
    expect(cn('p-4', 'p-2')).toBe('p-2')
  })
})

describe('isOnline', () => {
  it('returns false for null', () => {
    expect(isOnline(null)).toBe(false)
  })

  it('returns true for recent timestamp', () => {
    const recent = new Date(Date.now() - 30 * 60 * 1000).toISOString() // 30 min ago
    expect(isOnline(recent)).toBe(true)
  })

  it('returns false for old timestamp', () => {
    const old = new Date(Date.now() - 3 * 60 * 60 * 1000).toISOString() // 3 hours ago
    expect(isOnline(old)).toBe(false)
  })
})

describe('timeAgo', () => {
  it('returns seconds for recent', () => {
    const now = new Date().toISOString()
    expect(timeAgo(now)).toMatch(/\d+s ago/)
  })

  it('returns minutes', () => {
    const fiveMinAgo = new Date(Date.now() - 5 * 60 * 1000).toISOString()
    expect(timeAgo(fiveMinAgo)).toBe('5m ago')
  })

  it('returns hours', () => {
    const threeHoursAgo = new Date(Date.now() - 3 * 60 * 60 * 1000).toISOString()
    expect(timeAgo(threeHoursAgo)).toBe('3h ago')
  })

  it('returns days', () => {
    const twoDaysAgo = new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString()
    expect(timeAgo(twoDaysAgo)).toBe('2d ago')
  })
})
