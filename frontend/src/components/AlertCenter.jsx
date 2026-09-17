import { useMemo } from 'react'
import useStationSocket from '../hooks/useStationSocket'

export default function AlertCenter({ alerts = [], onSelectStation }) {
  const { latestData, connectionState } = useStationSocket()
  const socketIsLive = connectionState === 'open'
  const liveAlerts = useMemo(() => {
    if (!latestData?.station_id) return alerts

    const existingAlerts = alerts.filter((alert) => alert.station_id !== latestData.station_id)
    if (!latestData.anomaly?.is_anomaly) return existingAlerts

    const existingStation = alerts.find((alert) => alert.station_id === latestData.station_id)
    return [{
      ...latestData,
      name: existingStation?.name || latestData.station_id,
      city: existingStation?.city,
      state: existingStation?.state,
      country: existingStation?.country,
      feedUrl: existingStation?.feedUrl,
    }, ...existingAlerts]
  }, [alerts, latestData])

  return (
    <div className="alert-center">
      <div className="alert-center-heading">
        <h3 className="alert-center-title">Anomaly alert center</h3>
        <span className={`socket-status socket-status--${socketIsLive ? 'live' : 'disconnected'}`} role="status" aria-live="polite">
          <span className="socket-status-dot" aria-hidden="true" />
          {socketIsLive ? 'Live' : 'Disconnected'}
        </span>
      </div>
      {liveAlerts.length === 0 && <p className="alert-empty mono">No active anomalies.</p>}
      {liveAlerts.map(a => {
        const time = a.timestamp 
          ? new Date(a.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) 
          : '--:--'
        
        const stationLabel = a.name || a.station_id
        const anomalyType = a.anomaly?.type || 'unknown'
        const affectedParam = a.affected_parameter || a.anomaly?.affected_parameter || 'general'
        const confidencePct = a.anomaly?.confidence != null 
          ? `${Math.round(a.anomaly.confidence * 100)}%` 
          : 'N/A'

        return (
          <button 
            key={a.station_id} 
            className="alert-item" 
            onClick={() => onSelectStation(a.station_id)}
          >
            <span className="alert-item-dot" />
            <div className="alert-item-body">
              <span className="alert-item-title">
                {stationLabel} <span className="mono">· {anomalyType}</span>
              </span>
              <span className="alert-item-sub">
                {time} · {affectedParam} · <span style={{ whiteSpace: 'nowrap' }}>{confidencePct} confidence</span>
              </span>
            </div>
          </button>
        )
      })}
    </div>
  )
}