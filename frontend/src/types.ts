export type Severity = 'warning' | 'critical'
export type Actor = {
  id: string
  kind: 'worker' | 'excavator' | 'truck' | 'forklift'
  label: string
  x: number
  y: number
  vx: number
  vy: number
  heading: number
}
export type Zone = {
  id: string
  label: string
  x: number
  y: number
  width: number
  height: number
  restricted: boolean
}
export type Hazard = {
  id: string
  severity: Severity
  category: 'proximity' | 'projected_collision' | 'restricted_zone'
  description: string
  actor_ids: string[]
  distance_m: number | null
  time_to_closest_s: number | null
  minimum_separation_m: number | null
}
export type Incident = Hazard & { detected_at: string }
export type SiteSnapshot = {
  site_id: string
  name: string
  timestamp: string
  elapsed_s: number
  width_m: number
  height_m: number
  mode: 'simulation'
  actors: Actor[]
  zones: Zone[]
  hazards: Hazard[]
  incidents_total: number
  people_on_site: number
  equipment_active: number
}
