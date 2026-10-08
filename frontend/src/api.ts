import type { Incident, SiteSnapshot } from './types'

const API_BASE = (import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(API_BASE + path, { cache: 'no-store' })
  if (!response.ok) throw new Error(`API request failed (HTTP ${response.status})`)
  return response.json() as Promise<T>
}

export function loadSite() {
  return getJson<SiteSnapshot>('/api/site')
}
export function loadIncidents() {
  return getJson<Incident[]>('/api/incidents?limit=30')
}
