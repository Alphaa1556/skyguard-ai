import { useEffect, useMemo, useState } from 'react'
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
} from 'recharts'
import { STATIONS, fetchStationStatus } from '../data/mockStations'
import './Dashboard.css'
import AlertCenter from './AlertCenter'

const HEALTH_META = {
  normal: { label: 'Normal', color: 'var(--teal)', dim: 'var(--teal-dim)' },
  nominal: { label: 'Normal', color: 'var(--teal)', dim: 'var(--teal-dim)' },
  degraded: { label: 'Degraded', color: 'var(--amber)', dim: 'var(--amber-dim)' },
  anomaly: { label: 'Anomaly', color: 'var(--red)', dim: 'var(--red-dim)' },
}

function Badge({ health }) {
  const meta = HEALTH_META[health] || HEALTH_META.normal
  return (
    <span className="badge mono" style={{ color: meta.color, background: meta.dim }}>
      <span className="badge-dot" style={{ background: meta.color }} />
      {meta.label}
    </span>
  )
}

// Fixed padding per metric keeps the Y-axis stable across polls instead of
// auto-rescaling on every tiny jitter in the mock data (or real sensor noise).
const METRIC_DOMAIN = {
  temperature_c: { pad: 2, min: undefined, max: undefined },
  pressure_hpa: { pad: 3, min: undefined, max: undefined },
  humidity_pct: { pad: 6, min: 0, max: 100 },
}

function getDomain(data, dataKey) {
  const cfg = METRIC_DOMAIN[dataKey] || { pad: 2 }
  const values = data.map(d => d[dataKey]).filter(v => typeof v === 'number')
  if (!values.length) return ['auto', 'auto']
  let lo = Math.floor(Math.min(...values) - cfg.pad)
  let hi = Math.ceil(Math.max(...values) + cfg.pad)
  if (cfg.min !== undefined) lo = Math.max(lo, cfg.min)
  if (cfg.max !== undefined) hi = Math.min(hi, cfg.max)
  return [lo, hi]
}

function MetricChart({ data, dataKey, label, unit, color }) {
  const domain = useMemo(() => getDomain(data, dataKey), [data, dataKey])
  return (
    <div className="metric-chart">
      <div className="metric-chart-head">
        <span className="metric-chart-label">{label}</span>
        <span className="metric-chart-value mono">
          {data[data.length - 1]?.[dataKey]}
          <span className="metric-chart-unit">{unit}</span>
        </span>
      </div>
      <ResponsiveContainer width="100%" height={110}>
        <LineChart data={data} margin={{ top: 6, right: 4, left: -20, bottom: 0 }}>
          <CartesianGrid stroke="var(--border)" vertical={false} />
          <XAxis dataKey="time" tick={{ fill: 'var(--text-faint)', fontSize: 10 }} axisLine={false} tickLine={false} interval={7} />
          <YAxis domain={domain} tick={{ fill: 'var(--text-faint)', fontSize: 10 }} axisLine={false} tickLine={false} width={34} />
          <Tooltip
            contentStyle={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-strong)', borderRadius: 8, fontSize: 12 }}
            labelStyle={{ color: 'var(--text-muted)' }}
          />
          <Line type="monotone" dataKey={dataKey} stroke={color} strokeWidth={2} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

// "Updated Xs ago" — ticks every second off a fetchedAt timestamp stamped
// onto each station's status when it's polled.
function LastUpdated({ fetchedAt }) {
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])
  if (!fetchedAt) return null
  const secs = Math.max(0, Math.round((now - fetchedAt) / 1000))
  const text = secs < 1 ? 'just now' : secs === 1 ? '1s ago' : `${secs}s ago`
  return <span className="last-updated mono">Updated {text}</span>
}

export default function Dashboard() {
  const [selectedId, setSelectedId] = useState(STATIONS[0].station_id)
  const [statuses, setStatuses] = useState({})

  // Poll every station's /status on an interval — swap for WebSocket later if needed.
  useEffect(() => {
    let cancelled = false
    const load = async () => {
      const fetchedAt = Date.now()
      const entries = await Promise.all(
        STATIONS.map(async s => [s.station_id, { ...(await fetchStationStatus(s.station_id)), fetchedAt }])
      )
      if (!cancelled) setStatuses(Object.fromEntries(entries))
    }
    load()
    const interval = setInterval(load, 8000)
    return () => { cancelled = true; clearInterval(interval) }
  }, [])

  const alerts = useMemo(
    () => Object.values(statuses).filter(s => s?.anomaly?.is_anomaly),
    [statuses]
  )

  const selected = statuses[selectedId]

  return (
    <section className="dashboard" id="stations">
      <div className="dashboard-head">
        <div>
          <h2 className="section-title">Station network</h2>
          <p className="section-sub">Live readings across {STATIONS.length} Automatic Weather Stations</p>
        </div>
        <div className="live-indicator mono">
          <span className="status-pip" /> LIVE · polling every 8s
        </div>
      </div>

      <div className="dashboard-grid">
        <div className="station-list">
          {STATIONS.map(s => {
            const status = statuses[s.station_id]
            const health = status?.sensor_health || s.health
            return (
              <button
                key={s.station_id}
                className={`station-card ${selectedId === s.station_id ? 'station-card--active' : ''}`}
                onClick={() => setSelectedId(s.station_id)}
              >
                <div className="station-card-top">
                  <span className="station-name">{s.name}</span>
                  <Badge health={health} />
                </div>
                <span className="station-id mono">{s.station_id}</span>
                {status?.anomaly?.is_anomaly && (
                  <span className="station-anomaly-type mono">{status.anomaly.type}</span>
                )}
              </button>
            )
          })}
        </div>

        <div className="station-detail">
          {selected ? (
            <>
              <div className="detail-head">
                <div>
                  <h3 className="detail-title">{selected.name}</h3>
                  <span className="detail-id mono">{selected.station_id}</span>
                </div>
                <div className="detail-head-right">
                  <Badge health={selected.sensor_health} />
                  <LastUpdated fetchedAt={selected.fetchedAt} />
                </div>
              </div>

              {selected.anomaly?.is_anomaly && (
                <div className="explain-panel">
                  <div className="explain-panel-head">
                    <span className="explain-panel-type mono">{selected.anomaly.type.toUpperCase()}</span>
                    <div className="confidence-bar">
                      <div className="confidence-bar-track">
                        <div className="confidence-bar-fill" style={{ width: `${selected.anomaly.confidence * 100}%` }} />
                      </div>
                      <span className="confidence-value mono">{Math.round(selected.anomaly.confidence * 100)}% confidence</span>
                    </div>
                  </div>
                  <p className="explain-panel-text">{selected.anomaly.explanation}</p>
                </div>
              )}

              <div className="metric-grid">
                <MetricChart data={selected.series} dataKey="temperature_c" label="Temperature" unit="°C" color="var(--teal)" />
                <MetricChart data={selected.series} dataKey="pressure_hpa" label="Pressure" unit=" hPa" color="#6FE8FF" />
                <MetricChart data={selected.series} dataKey="humidity_pct" label="Humidity" unit="%" color="var(--amber)" />
              </div>
            </>
          ) : (
            <div className="detail-loading mono">Loading station telemetry…</div>
          )}
        </div>

       <AlertCenter alerts={alerts} onSelectStation={setSelectedId} />
      </div>
    </section>
  )
}
