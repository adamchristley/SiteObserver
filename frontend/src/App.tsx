import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  ScanSearch, Activity, AlertTriangle, ArrowUpRight, BellRing, CheckCircle2, ChevronDown,
  CircleDot, Clock3, HardHat, LayoutDashboard, MapPinned, Pause, Play,
  Radio, RefreshCw, Shield, ShieldAlert, ShieldCheck, Truck, Users, Zap,
} from 'lucide-react'
import { loadIncidents, loadSite } from './api'
import VideoReview from './VideoReview'
import type { Actor, Hazard, Incident, SiteSnapshot } from './types'

type View = 'overview' | 'incidents' | 'vision'
type Sample = { tick: number; risks: number }

function formatTime(value: string) {
  return new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}
function categoryLabel(category: Hazard['category']) {
  return ({
    proximity: 'Unsafe proximity',
    projected_collision: 'Projected close approach',
    restricted_zone: 'Restricted zone entry',
  })[category]
}
function Metric({ label, value, detail, icon: Icon, tone = 'normal' }: {
  label: string
  value: string | number
  detail: string
  icon: typeof Activity
  tone?: 'normal' | 'risk' | 'good'
}) {
  return (
    <article className={`metric-card ${tone}`}>
      <div className="metric-top"><span>{label}</span><Icon size={18} strokeWidth={1.7} /></div>
      <div className="metric-value">{value}</div>
      <div className="metric-detail"><span className="metric-dot" />{detail}</div>
    </article>
  )
}
function SceneIcon({ actor }: { actor: Actor }) {
  const position = `translate(${actor.x * 10} ${actor.y * 10})`
  const rotate = `rotate(${(actor.heading * 180) / Math.PI})`
  const isWorker = actor.kind === 'worker'
  return (
    <g transform={position} className="site-actor">
      <title>{actor.label}: ({actor.x.toFixed(1)}, {actor.y.toFixed(1)}) meters</title>
      {isWorker ? (
        <>
          <circle r="13" className="worker-halo" />
          <circle r="7" fill="#a8f28e" stroke="#102018" strokeWidth="2" />
          <circle r="2" fill="#102018" />
        </>
      ) : (
        <g transform={rotate}>
          <rect x="-21" y="-12" width="42" height="24" rx="5" fill="#efb76c" stroke="#242825" strokeWidth="2" />
          <rect x="-10" y="-8" width="16" height="16" rx="2" fill="#5a4b36" />
          <path d="M12 -7 L25 0 L12 7" stroke="#242825" strokeWidth="3" fill="none" />
          <rect x="-15" y="-17" width="12" height="4" rx="2" fill="#3b4038" />
          <rect x="-15" y="13" width="12" height="4" rx="2" fill="#3b4038" />
        </g>
      )}
      <text y={isWorker ? -19 : -24} textAnchor="middle" className="actor-name">{actor.id.toUpperCase()}</text>
    </g>
  )
}
function SiteMap({ snapshot, selected, onSelect }: {
  snapshot: SiteSnapshot
  selected: string | null
  onSelect: (id: string | null) => void
}) {
  const hazards = new Set(snapshot.hazards.flatMap(h => h.actor_ids))
  return (
    <div className="site-map-frame">
      <svg viewBox="0 0 800 500" className="site-map" role="img" aria-label="Top-down simulated construction site with workers and machinery">
        <defs>
          <pattern id="grid" width="50" height="50" patternUnits="userSpaceOnUse">
            <path d="M 50 0 L 0 0 0 50" fill="none" stroke="#668078" strokeWidth=".8" opacity=".18" />
          </pattern>
          <pattern id="danger-stripe" width="16" height="16" patternTransform="rotate(45)" patternUnits="userSpaceOnUse">
            <rect width="16" height="16" fill="#dba050" fillOpacity=".075" />
            <path d="M0 0V16" stroke="#dba050" strokeOpacity=".12" strokeWidth="5" />
          </pattern>
        </defs>
        <rect width="800" height="500" fill="#182320" />
        <rect width="800" height="500" fill="url(#grid)" />
        <path d="M0 295 H800" stroke="#9bafa4" strokeOpacity=".15" strokeWidth="74" />
        <path d="M0 295 H800" stroke="#c6d7c9" strokeOpacity=".22" strokeDasharray="16 18" strokeWidth="1.5" />
        <rect x="322" y="58" width="144" height="108" rx="4" fill="#9ab8a9" fillOpacity=".055" stroke="#99b7a6" strokeOpacity=".3" strokeDasharray="6 6" />
        <path d="M334 69h119v83H334zM340 83h106M340 100h106M340 117h106" stroke="#a0b9ab" strokeOpacity=".13" />
        <text x="395" y="182" textAnchor="middle" className="map-label">STAGING AREA</text>
        <path d="M60 420L137 338h165l70 82" fill="none" stroke="#96a69e" strokeWidth="1.5" strokeDasharray="7 6" opacity=".35" />
        <text x="193" y="445" className="map-label" textAnchor="middle">SITE ACCESS</text>
        {snapshot.zones.map(zone => (
          <g key={zone.id}>
            <rect
              x={zone.x * 10} y={zone.y * 10}
              width={zone.width * 10} height={zone.height * 10}
              rx="4"
              fill={zone.restricted ? 'url(#danger-stripe)' : '#83dbab'}
              fillOpacity={zone.restricted ? 1 : .06}
              stroke={zone.restricted ? '#dba050' : '#7dbba1'}
              strokeWidth="1.7"
              strokeDasharray="8 5"
            />
            <text x={zone.x * 10 + 12} y={zone.y * 10 + 19} className={zone.restricted ? 'zone-label restricted' : 'zone-label'}>{zone.label.toUpperCase()}</text>
          </g>
        ))}
        {snapshot.hazards.filter(h => h.actor_ids.length === 2).map(h => {
          const a = snapshot.actors.find(actor => actor.id === h.actor_ids[0])
          const b = snapshot.actors.find(actor => actor.id === h.actor_ids[1])
          if (!a || !b) return null
          return <line key={h.id} x1={a.x * 10} y1={a.y * 10} x2={b.x * 10} y2={b.y * 10} stroke={h.severity === 'critical' ? '#ef8973' : '#ecc179'} strokeWidth="2" strokeDasharray="5 5" opacity=".85" />
        })}
        {snapshot.actors.map(actor => (
          <g
            key={actor.id}
            role="button" tabIndex={0} aria-label={`Select ${actor.label}`}
            onClick={() => onSelect(selected === actor.id ? null : actor.id)}
            onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onSelect(selected === actor.id ? null : actor.id) } }}
            className="map-target"
          >
            {(hazards.has(actor.id) || selected === actor.id) && (
              <circle cx={actor.x * 10} cy={actor.y * 10} r={selected === actor.id ? 29 : 23} fill="none" stroke={selected === actor.id ? '#a8f28e' : '#ef8973'} strokeWidth="1.5" opacity=".7" strokeDasharray={selected === actor.id ? undefined : '3 4'} />
            )}
            <SceneIcon actor={actor} />
          </g>
        ))}
        <path d="M760 60v-25m0 0 -7 10m7-10 7 10" stroke="#9fb9ab" strokeWidth="2" fill="none" />
        <text x="760" y="27" textAnchor="middle" className="north-label">N</text>
        <path d="M32 462h100m-100-5v10m100-10v10" stroke="#c0d6c6" strokeOpacity=".6" />
        <text x="82" y="483" textAnchor="middle" className="map-label">10 METERS</text>
      </svg>
      <div className="map-label-top"><span className="signal-dot" /> LIVE SITE SIMULATION <span className="map-coords">80 × 50 M</span></div>
      <div className="map-legend"><span><i className="legend-worker" /> Workers</span><span><i className="legend-vehicle" /> Equipment</span><span><i className="legend-alert" /> Risk pairing</span></div>
    </div>
  )
}
function Trend({ samples }: { samples: Sample[] }) {
  const points = useMemo(() => {
    if (samples.length < 2) return ''
    const max = Math.max(3, ...samples.map(s => s.risks))
    return samples.map((s, i) => `${8 + (i / (samples.length - 1)) * 384},${120 - (s.risks / max) * 92}`).join(' ')
  }, [samples])
  return (
    <div className="trend-chart">
      <div className="trend-axis"><span>RISK EVENTS</span><span>LIVE WINDOW</span></div>
      <svg viewBox="0 0 400 140" preserveAspectRatio="none" role="img" aria-label="Recent active hazard count trend">
        {[28, 58, 89, 120].map(y => <line key={y} x1="0" y1={y} x2="400" y2={y} stroke="#64756c" strokeOpacity=".2" strokeDasharray="4 5" />)}
        {points && <polyline points={points} fill="none" stroke="#a8f28e" strokeWidth="2.6" strokeLinejoin="round" strokeLinecap="round" />}
        {points && <circle cx="392" cy={Number(points.split(' ').at(-1)?.split(',')[1])} r="4" fill="#a8f28e" stroke="#1b2723" strokeWidth="3" />}
      </svg>
      <div className="trend-axis"><span>EARLIER</span><span>NOW</span></div>
    </div>
  )
}
function HazardList({ hazards }: { hazards: Hazard[] }) {
  if (!hazards.length) return <div className="empty-state"><ShieldCheck size={30} /><strong>No active hazards</strong><p>All monitored objects currently meet baseline proximity rules.</p></div>
  return <div className="hazard-list">{hazards.map(h => (
    <div className="hazard-row" key={h.id}>
      <div className={`hazard-symbol ${h.severity}`}><AlertTriangle size={17} /></div>
      <div className="hazard-copy"><strong>{categoryLabel(h.category)}</strong><span>{h.description}</span><small>{h.actor_ids.join(' · ').toUpperCase()}</small></div>
      <span className={`severity-pill ${h.severity}`}>{h.severity}</span>
    </div>
  ))}</div>
}
export default function App() {
  const [snapshot, setSnapshot] = useState<SiteSnapshot | null>(null)
  const [incidents, setIncidents] = useState<Incident[]>([])
  const [samples, setSamples] = useState<Sample[]>([])
  const [running, setRunning] = useState(true)
  const [view, setView] = useState<View>('overview')
  const [selected, setSelected] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const refresh = useCallback(async () => {
    try {
      const [site, events] = await Promise.all([loadSite(), loadIncidents()])
      setSnapshot(site)
      setIncidents(events)
      setSamples(prev => [...prev.slice(-30), { tick: site.elapsed_s, risks: site.hazards.length }])
      setError(null)
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Unable to connect to the API')
    }
  }, [])
  useEffect(() => {
    if (!running) return
    void refresh()
    const timer = window.setInterval(() => { void refresh() }, 1200)
    return () => window.clearInterval(timer)
  }, [running, refresh])
  const critical = snapshot?.hazards.filter(h => h.severity === 'critical').length ?? 0
  const activeCount = snapshot?.hazards.length ?? 0
  const selectedActor = snapshot?.actors.find(actor => actor.id === selected)
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark"><Shield size={23} strokeWidth={2.5} /><span /></div>
          <div><strong>SITE<span>OBSERVER</span></strong><small>SAFETY INTELLIGENCE</small></div>
        </div>
        <div className="side-section">WORKSPACE</div>
        <nav aria-label="Primary navigation">
          <button className={`nav-item ${view === 'overview' ? 'active' : ''}`} onClick={() => setView('overview')}><LayoutDashboard size={19} /> Overview</button>
          <button className={`nav-item ${view === 'incidents' ? 'active' : ''}`} onClick={() => setView('incidents')}><ShieldAlert size={19} /> Incident log <span className="nav-count">{incidents.length}</span></button>
          <button className={`nav-item ${view === 'vision' ? 'active' : '' }`} onClick={() => setView('vision')}><ScanSearch size={19} /> Video analysis</button>
        </nav>
        <div className="side-section site-title">MONITORED SITE</div>
        <div className="site-picker"><span className="site-picker-icon"><MapPinned size={17} /></span><div><strong>North Excavation</strong><small>Research site 01</small></div><ChevronDown size={16} /></div>
        <div className="sidebar-bottom">
          <div className="system-status"><Radio size={16} /><div><strong>Simulation mode</strong><small>No physical sensors connected</small></div></div>
          <div className="avatar-row"><div className="avatar">RE</div><div><strong>Research Workspace</strong><small>Local development</small></div></div>
        </div>
      </aside>
      <main className="main">
        <header className="topbar"><span><span className="topbar-location">Workspace</span><span className="slash">/</span>{view === 'overview' ? 'Overview' : view === 'vision' ? 'Video analysis' : 'Incident log'}</span><div className="topbar-right"><span className="connection"><span className={error ? 'offline-dot' : 'online-dot'} />{error ? 'API DISCONNECTED' : snapshot ? 'API CONNECTED' : 'CONNECTING'}</span><span className="topbar-divider" /><span className="date-label">{new Date().toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' })}</span></div></header>
        <div className="page">
          <div className="heading-row"><div><div className="eyebrow"><span className="eyebrow-line" /> SAFETY OPERATIONS / LIVE MONITORING</div><h1>{view === 'overview' ? 'Site overview' : view === 'vision' ? 'Video analysis' : 'Incident history'}</h1><p className="subtitle">{view === 'overview' ? 'Real-time awareness of worker safety and equipment activity.' : view === 'vision' ? 'Detect and track objects in recorded construction-site footage.' : 'Recorded changes in simulated safety events. Newest events appear first.'}</p></div><div className="actions"><button className="btn btn-outline" onClick={() => { void refresh() }}><RefreshCw size={16} /> Refresh</button><button className="btn btn-primary" onClick={() => setRunning(prev => !prev)}>{running ? <Pause size={16} fill="currentColor" /> : <Play size={16} fill="currentColor" />}{running ? 'Pause updates' : 'Resume updates'}</button></div></div>
          <div className="demo-notice"><CircleDot size={16} /><div><strong>Research prototype</strong><span> Synthetic trajectories and rule-based hazards. Not a deployed safety device or validated collision predictor.</span></div><span className="notice-tag">DEMO DATA</span></div>
          {error && <div className="error-banner"><AlertTriangle size={18} /><span>{error}. Start the FastAPI backend on port 8000.</span><button onClick={() => { void refresh() }}>Retry</button></div>}
          {view === 'vision' ? <VideoReview /> : <>
          <section className="metrics-grid" aria-label="Operational metrics">
            <Metric label="Workers on site" value={snapshot?.people_on_site ?? '—'} detail="Simulated personnel" icon={Users} />
            <Metric label="Active equipment" value={snapshot?.equipment_active ?? '—'} detail="Tracked machinery" icon={Truck} />
            <Metric label="Active hazards" value={snapshot ? activeCount : '—'} detail={critical ? `${critical} critical risk${critical === 1 ? '' : 's'}` : 'No critical conditions'} icon={ShieldAlert} tone={critical ? 'risk' : 'good'} />
            <Metric label="Incidents logged" value={snapshot?.incidents_total ?? '—'} detail="Current simulation session" icon={Activity} />
          </section>
          {view === 'overview' ? (
            <>
              <div className="content-grid">
                <section className="panel map-panel">
                  <div className="panel-head"><div><span className="section-kicker">SPATIAL INTELLIGENCE</span><h2>Live site map</h2></div><span className="live-tag"><span className="pulse-dot" />{running ? 'LIVE UPDATES' : 'UPDATES PAUSED'}</span></div>
                  {snapshot ? <SiteMap snapshot={snapshot} selected={selected} onSelect={setSelected} /> : <div className="loading-map">Waiting for site telemetry...</div>}
                  <div className="map-footer"><div><span className="footer-label">COORDINATES</span><strong>{selectedActor ? `${selectedActor.x.toFixed(1)}, ${selectedActor.y.toFixed(1)} m` : 'Select a map object to inspect'}</strong></div><div><span className="footer-label">LAST UPDATE</span><strong>{snapshot ? formatTime(snapshot.timestamp) : '—'}</strong></div></div>
                </section>
                <section className="panel activity-panel">
                  <div className="panel-head"><div><span className="section-kicker">SAFETY SIGNALS</span><h2>Active alerts</h2></div><span className="count-tag">{activeCount} ACTIVE</span></div>
                  <HazardList hazards={snapshot?.hazards ?? []} />
                  <button className="panel-link" onClick={() => setView('incidents')}>View incident history <ArrowUpRight size={16} /></button>
                </section>
              </div>
              <div className="bottom-grid">
                <section className="panel trend-panel"><div className="panel-head"><div><span className="section-kicker">RISK ANALYTICS</span><h2>Active hazard trend</h2></div><span className="subtle-tag">LAST {samples.length} SAMPLES</span></div><Trend samples={samples} /></section>
                <section className="panel operations-panel"><div className="panel-head"><div><span className="section-kicker">OPERATIONS SUMMARY</span><h2>System health</h2></div><CheckCircle2 size={19} className="green-icon" /></div><div className="health-row"><div className="health-icon"><Zap size={18} /></div><div><strong>Geometric risk engine</strong><span>Constant-velocity projection · 4s horizon</span></div><span className="health-value">ACTIVE</span></div><div className="health-row"><div className="health-icon"><Clock3 size={18} /></div><div><strong>Telemetry updates</strong><span>Poll interval · 1.2 seconds</span></div><span className="health-value">{running ? 'RUNNING' : 'PAUSED'}</span></div><div className="health-row"><div className="health-icon"><HardHat size={18} /></div><div><strong>Vision inference</strong><span>Planned development milestone</span></div><span className="health-pending">NOT ENABLED</span></div></section>
              </div>
            </>
          ) : (
            <section className="panel incidents-panel">
              <div className="panel-head"><div><span className="section-kicker">AUDIT HISTORY</span><h2>Safety incidents</h2></div><span className="count-tag">{incidents.length} SHOWN</span></div>
              <div className="incident-table-wrap"><table className="incident-table"><thead><tr><th>SEVERITY</th><th>EVENT</th><th>ENTITIES</th><th>DETECTED AT</th></tr></thead><tbody>
                {incidents.map((incident, index) => <tr key={`${incident.id}:${incident.detected_at}:${index}`}><td><span className={`severity-pill ${incident.severity}`}>{incident.severity}</span></td><td><strong>{categoryLabel(incident.category)}</strong><span>{incident.description}</span></td><td>{incident.actor_ids.join(', ').toUpperCase()}</td><td>{formatTime(incident.detected_at)}</td></tr>)}
                {!incidents.length && <tr><td colSpan={4} className="empty-table">No events recorded in the current session.</td></tr>}
              </tbody></table></div>
              <div className="table-note"><BellRing size={15} /> Events are recorded when a hazard starts or changes severity, not on every refresh.</div>
            </section>
          )}
          </>}
          <footer className="footer"><span>© {new Date().getFullYear()} SITEOBSERVER <span className="footer-sep">/</span> RESEARCH PROTOTYPE</span><span><span className="online-dot" /> LOCAL-FIRST · $0 CLOUD SPEND</span></footer>
        </div>
      </main>
    </div>
  )
}
