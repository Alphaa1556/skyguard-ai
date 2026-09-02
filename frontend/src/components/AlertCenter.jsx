export default function AlertCenter({ alerts = [], onSelectStation }) {
  return (
    <div className="alert-center">
      <h3 className="alert-center-title">Anomaly alert center</h3>
      {alerts.length === 0 && <p className="alert-empty mono">No active anomalies.</p>}
      {alerts.map(a => {
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