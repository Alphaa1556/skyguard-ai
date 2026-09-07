import { useEffect, useMemo, useState } from 'react'
import { fetchStations, fetchStationStatus } from '../data/stations'
import { loadLog, appendEntries, clearLog } from '../data/historicalLog'
import './HistoricalExplorer.css'

const POLL_INTERVAL_MS = 8000

const TYPE_LABELS = {
  spike: 'Spike',
  flatline: 'Flatline',
  drift: 'Drift',
  noise: 'Noise',
  cross_sensor: 'Cross-sensor',
}

function formatTime(ts) {
  try {
    return new Date(ts).toLocaleString(undefined, {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit',
    })
  } catch {
    return ts
  }
}

export default function HistoricalExplorer() {
  const [log, setLog] = useState(() => loadLog())
  const [stationFilter, setStationFilter] = useState('all')
  const [typeFilter, setTypeFilter] = useState('all')
  const [minConfidence, setMinConfidence] = useState(0)
  const [search, setSearch] = useState('')
  const [sortDir, setSortDir] = useState('desc') // 'desc' = newest first
  const [connectionOk, setConnectionOk] = useState(true)

  // Poll every station's status on an interval and log any anomaly seen.
  // Reuses the team's fetchStations()/fetchStationStatus() from data/stations.js,
  // which already handles the real backend URL and falls back gracefully
  // (with is_anomaly: false) if the backend is briefly unreachable — so this
  // never logs a false anomaly purely from a dropped connection.
  useEffect(() => {
    let cancelled = false
    let stationsCache = []

    const ensureStations = async () => {
      if (stationsCache.length) return stationsCache
      try {
        stationsCache = await fetchStations()
        return stationsCache
      } catch {
        return []
      }
    }

    const poll = async () => {
      const stations = await ensureStations()
      if (!stations.length) {
        if (!cancelled) setConnectionOk(false)
        return
      }
      const results = await Promise.allSettled(stations.map(s => fetchStationStatus(s.station_id)))
      if (cancelled) return

      setConnectionOk(results.some(r => r.status === 'fulfilled'))

      const newEntries = []
      results.forEach(r => {
        if (r.status !== 'fulfilled') return
        const status = r.value
        if (!status?.anomaly?.is_anomaly) return
        newEntries.push({
          id: `${status.station_id}__${status.timestamp}`,
          station_id: status.station_id,
          station_name: status.name || status.station_id,
          timestamp: status.timestamp,
          type: status.anomaly.type,
          confidence: status.anomaly.confidence,
          affected_parameter: status.anomaly.affected_parameter,
          explanation: status.anomaly.explanation,
        })
      })

      if (newEntries.length) {
        setLog(prev => appendEntries(prev, newEntries))
      }
    }

    poll()
    const interval = setInterval(poll, POLL_INTERVAL_MS)
    return () => { cancelled = true; clearInterval(interval) }
  }, [])

  const stationOptions = useMemo(() => {
    const ids = new Set(log.map(e => e.station_id))
    return Array.from(ids).sort()
  }, [log])

  const filtered = useMemo(() => {
    let rows = log
    if (stationFilter !== 'all') rows = rows.filter(e => e.station_id === stationFilter)
    if (typeFilter !== 'all') rows = rows.filter(e => e.type === typeFilter)
    if (minConfidence > 0) rows = rows.filter(e => e.confidence >= minConfidence)
    if (search.trim()) {
      const q = search.trim().toLowerCase()
      rows = rows.filter(e =>
        e.explanation?.toLowerCase().includes(q) ||
        e.station_name?.toLowerCase().includes(q) ||
        e.station_id?.toLowerCase().includes(q)
      )
    }
    return [...rows].sort((a, b) =>
      sortDir === 'desc'
        ? new Date(b.timestamp) - new Date(a.timestamp)
        : new Date(a.timestamp) - new Date(b.timestamp)
    )
  }, [log, stationFilter, typeFilter, minConfidence, search, sortDir])

  const handleClear = () => {
    if (window.confirm('Clear the entire logged anomaly history? This cannot be undone.')) {
      setLog(clearLog())
    }
  }

  return (
    <section className="explorer" id="history">
      <div className="explorer-head">
        <div>
          <h2 className="section-title">Historical data explorer</h2>
          <p className="section-sub">
            {log.length} anomal{log.length === 1 ? 'y' : 'ies'} logged since this page started watching
            {!connectionOk && <span className="explorer-conn-warning mono"> · backend unreachable, log paused</span>}
          </p>
        </div>
        <button className="explorer-clear-btn mono" onClick={handleClear} disabled={!log.length}>
          Clear log
        </button>
      </div>

      <div className="explorer-filters">
        <input
          className="explorer-search mono"
          type="text"
          placeholder="Search explanation or station…"
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
        <select className="explorer-select mono" value={stationFilter} onChange={e => setStationFilter(e.target.value)}>
          <option value="all">All stations</option>
          {stationOptions.map(id => <option key={id} value={id}>{id}</option>)}
        </select>
        <select className="explorer-select mono" value={typeFilter} onChange={e => setTypeFilter(e.target.value)}>
          <option value="all">All types</option>
          {Object.entries(TYPE_LABELS).map(([val, label]) => (
            <option key={val} value={val}>{label}</option>
          ))}
        </select>
        <select
          className="explorer-select mono"
          value={minConfidence}
          onChange={e => setMinConfidence(Number(e.target.value))}
        >
          <option value={0}>Any confidence</option>
          <option value={0.5}>≥ 50%</option>
          <option value={0.7}>≥ 70%</option>
          <option value={0.9}>≥ 90%</option>
        </select>
        <button
          className="explorer-sort-btn mono"
          onClick={() => setSortDir(d => (d === 'desc' ? 'asc' : 'desc'))}
        >
          {sortDir === 'desc' ? 'Newest first ↓' : 'Oldest first ↑'}
        </button>
      </div>

      <div className="explorer-table-wrap">
        {filtered.length === 0 ? (
          <div className="explorer-empty mono">
            {log.length === 0
              ? 'No anomalies logged yet — this fills in as the dashboard polls and flags real readings.'
              : 'No entries match the current filters.'}
          </div>
        ) : (
          <table className="explorer-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Station</th>
                <th>Type</th>
                <th>Parameter</th>
                <th>Confidence</th>
                <th>Explanation</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(e => (
                <tr key={e.id}>
                  <td className="mono explorer-cell-time">{formatTime(e.timestamp)}</td>
                  <td>
                    <div className="explorer-station-name">{e.station_name}</div>
                    <div className="explorer-station-id mono">{e.station_id}</div>
                  </td>
                  <td>
                    <span className={`explorer-type-pill explorer-type-pill--${e.type}`}>
                      {TYPE_LABELS[e.type] || e.type}
                    </span>
                  </td>
                  <td className="mono">{e.affected_parameter || '—'}</td>
                  <td className="mono">{Math.round((e.confidence || 0) * 100)}%</td>
                  <td className="explorer-cell-explanation">{e.explanation}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  )
}
