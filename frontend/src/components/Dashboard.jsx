import { useEffect, useMemo, useState } from 'react'
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
} from 'recharts'
import './Dashboard.css'
import AlertCenter from './AlertCenter'
import SensorBadge from './SensorBadge'
import ExplainPanel from './ExplainPanel'
import { DEFAULT_STATIONS, fetchStations } from '../data/stations'

const API_BASE = 'http://127.0.0.1:8000'

const METRIC_DOMAIN = {
  temperature_c: { pad: 2, min: undefined, max: undefined },
  pressure_hpa: { pad: 3, min: undefined, max: undefined },
  humidity_pct: { pad: 6, min: 0, max: 100 },
}

function getDomain(data, dataKey) {
  if (!data) return ['auto', 'auto']
  const cfg = METRIC_DOMAIN[dataKey] || { pad: 2 }
  const values = data.map((d) => d[dataKey]).filter((value) => typeof value === 'number')
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

export default function Dashboard({ selectedStationId, onSelectStation }) {
  const [stations, setStations] = useState(DEFAULT_STATIONS)
  const [selectedId, setSelectedId] = useState(selectedStationId || DEFAULT_STATIONS[0]?.station_id || null)
  const [statuses, setStatuses] = useState({})

  useEffect(() => {
    let active = true

    fetchStations()
      .then((items) => {
        if (!active) return
        setStations(items)
        setSelectedId((current) => current || selectedStationId || items[0]?.station_id || DEFAULT_STATIONS[0]?.station_id || null)
      })
      .catch(() => {
        if (active) setStations(DEFAULT_STATIONS)
      })

    return () => {
      active = false
    }
  }, [selectedStationId])

  useEffect(() => {
    if (selectedStationId) {
      setSelectedId(selectedStationId)
    }
  }, [selectedStationId])

  useEffect(() => {
    if (!selectedId) return

    const stationCards = document.querySelectorAll('.station-card')
    stationCards.forEach((card) => {
      const isActive = card.getAttribute('data-station-id') === selectedId
      if (isActive) {
        card.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
      }
    })
  }, [selectedId])

  useEffect(() => {
    let cancelled = false

    const load = async () => {
      try {
        const stationList = await fetchStations()
        if (cancelled) return

        setStations(stationList)
        if (!selectedId && stationList.length > 0) {
          setSelectedId(stationList[0].station_id)
        }

        const entries = await Promise.all(
          stationList.map(async (station) => {
            const previousSeries = statuses[station.station_id]?.series || []
            const response = await fetch(`${API_BASE}/stations/${station.station_id}/status`)
            const statusData = response.ok ? await response.json() : null

            const timestamp = statusData?.timestamp ? new Date(statusData.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : ''
            const latestReading = statusData?.readings || {}
            const newPoint = {
              time: timestamp,
              temperature_c: latestReading.temperature_c,
              pressure_hpa: latestReading.pressure_hpa,
              humidity_pct: latestReading.humidity_pct,
            }

            const series = [...previousSeries, newPoint].filter((point) => point.time || point.temperature_c !== undefined || point.pressure_hpa !== undefined || point.humidity_pct !== undefined).slice(-30)

            return [
              station.station_id,
              {
                ...statusData,
                station_id: station.station_id,
                name: station.name || statusData?.name || station.station_id,
                city: station.city || statusData?.city || station.station_id,
                state: station.state || statusData?.state || 'India',
                country: station.country || statusData?.country || 'India',
                feedUrl: station.feedUrl || statusData?.feedUrl || statusData?.feed_url || 'https://mausam.imd.gov.in/',
                sensor_health: statusData?.sensor_health || station.health || 'normal',
                fetchedAt: Date.now(),
                series,
              },
            ]
          })
        )

        if (!cancelled) {
          setStatuses((previous) => {
            const next = { ...previous }
            entries.forEach(([id, value]) => {
              next[id] = value
            })
            return next
          })
        }
      } catch (error) {
        console.error('Backend fetch failed:', error)
      }
    }

    load()
    const interval = setInterval(load, 8000)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [selectedId])

  const alerts = useMemo(
    () => Object.values(statuses).filter((status) => status?.anomaly?.is_anomaly),
    [statuses]
  )

  const selected = statuses[selectedId] || stations.find((station) => station.station_id === selectedId) || null

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
          {stations.map((station) => {
            const status = statuses[station.station_id]
            const health = status?.sensor_health || station.health || 'normal'
            const name = station.name || station.station_id

            return (
              <button
                key={station.station_id}
                data-station-id={station.station_id}
                className={`station-card ${selectedId === station.station_id ? 'station-card--active' : ''}`}
                onClick={() => {
                  setSelectedId(station.station_id)
                  if (onSelectStation) onSelectStation(station.station_id)
                }}
              >
                <div className="station-card-top">
                  <span className="station-name">{name}</span>
                  <SensorBadge health={health} />
                </div>
                <span className="station-id mono">{station.station_id}</span>
                <span className="station-location mono">{station.city}, {station.state}, {station.country || 'India'}</span>
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
                  <a href={selected.feedUrl || selected.feed_url} target="_blank" rel="noreferrer" className="detail-feed-link">
                    Live feed
                  </a>
                </div>
              </div>

              <ExplainPanel anomaly={selected.anomaly} />

              <div className="current-readings" aria-label="Current station readings">
                <div className="current-reading"><span>Temperature</span><strong>{selected.readings?.temperature_c ?? '--'}<small> °C</small></strong></div>
                <div className="current-reading"><span>Pressure</span><strong>{selected.readings?.pressure_hpa ?? '--'}<small> hPa</small></strong></div>
                <div className="current-reading"><span>Humidity</span><strong>{selected.readings?.humidity_pct ?? '--'}<small> %</small></strong></div>
              </div>

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