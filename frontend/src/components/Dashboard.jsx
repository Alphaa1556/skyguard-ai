import { useEffect, useMemo, useState } from 'react'
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
} from 'recharts'
import './Dashboard.css'
import AlertCenter from './AlertCenter'
import SensorBadge from './SensorBadge'
import ExplainPanel from './ExplainPanel'

const API_BASE = 'http://127.0.0.1:8000'

const METRIC_DOMAIN = {
  temperature_c: { pad: 2, min: undefined, max: undefined },
  pressure_hpa: { pad: 3, min: undefined, max: undefined },
  humidity_pct: { pad: 6, min: 0, max: 100 },
}

function getDomain(data, dataKey) {
  if (!data) return ['auto', 'auto']
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
  const latestValue = data && data.length > 0 ? data[data.length - 1]?.[dataKey] : '--'

  return (
    <div className="metric-chart">
      <div className="metric-chart-head">
        <span className="metric-chart-label">{label}</span>
        <span className="metric-chart-value mono">
          {latestValue}
          <span className="metric-chart-unit">{unit}</span>
        </span>
      </div>
      <ResponsiveContainer width="100%" height={110}>
        <LineChart data={data || []} margin={{ top: 6, right: 4, left: -20, bottom: 0 }}>
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
  const [stations, setStations] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [statuses, setStatuses] = useState({})

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const stationsRes = await fetch(`${API_BASE}/stations`)
        const stationsData = await stationsRes.json()
        
        if (!cancelled) {
          setStations(stationsData)
          if (!selectedId && stationsData.length > 0) setSelectedId(stationsData[0].station_id)
        }

        const fetchedAt = Date.now()
        
        setStatuses(prev => {
          const newStatuses = { ...prev }
          return Promise.all(
            stationsData.map(async s => {
              const statusRes = await fetch(`${API_BASE}/stations/${s.station_id}/status`)
              const statusData = await statusRes.json()
              
              const currentSeries = newStatuses[s.station_id]?.series || []
              const timeString = statusData.timestamp ? new Date(statusData.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : ''
              
              const newPoint = { 
                time: timeString, 
                temperature_c: statusData.readings?.temperature_c,
                pressure_hpa: statusData.readings?.pressure_hpa,
                humidity_pct: statusData.readings?.humidity_pct
              }
              
              const updatedSeries = [...currentSeries, newPoint].slice(-30)

              return [s.station_id, { ...statusData, fetchedAt, series: updatedSeries }]
            })
          ).then(entries => {
            if (!cancelled) {
              setStatuses(Object.fromEntries(entries))
            }
          }).catch(err => console.error("Error mapping statuses", err))
          
          return prev
        })
      } catch (err) {
        console.error("Backend fetch failed:", err)
      }
    }
    
    load()
    const interval = setInterval(load, 8000)
    return () => { cancelled = true; clearInterval(interval) }
  }, [selectedId])

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
          <p className="section-sub">Live readings across {stations.length} Automatic Weather Stations</p>
        </div>
        <div className="live-indicator mono">
          <span className="status-pip" /> LIVE · polling every 8s
        </div>
      </div>

      <div className="dashboard-grid">
        <div className="station-list">
          {stations.map(s => {
            const status = statuses[s.station_id]
            const health = status?.sensor_health || s.health || 'normal'
            const name = s.name || s.station_id
            return (
              <button
                key={s.station_id}
                className={`station-card ${selectedId === s.station_id ? 'station-card--active' : ''}`}
                onClick={() => setSelectedId(s.station_id)}
              >
                <div className="station-card-top">
                  <span className="station-name">{name}</span>
                  <SensorBadge health={health} />
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
                  <h3 className="detail-title">{selected.name || selected.station_id}</h3>
                  <span className="detail-id mono">{selected.station_id}</span>
                </div>
                <div className="detail-head-right">
                  <SensorBadge health={selected.sensor_health || 'normal'} />
                  <LastUpdated fetchedAt={selected.fetchedAt} />
                </div>
              </div>

              <ExplainPanel anomaly={selected.anomaly} />

              <div className="metric-grid">
                <MetricChart data={selected.series} dataKey="temperature_c" label="Temperature" unit="°C" color="var(--teal)" />
                <MetricChart data={selected.series} dataKey="pressure_hpa" label="Pressure" unit=" hPa" color="#6FE8FF" />
                <MetricChart data={selected.series} dataKey="humidity_pct" label="Humidity" unit="%" color="var(--amber)" />
              </div>
            </>
          ) : (
            <div className="detail-loading mono">Loading station telemetry...</div>
          )}
        </div>

       <AlertCenter alerts={alerts} onSelectStation={setSelectedId} />
      </div>
    </section>
  )
}