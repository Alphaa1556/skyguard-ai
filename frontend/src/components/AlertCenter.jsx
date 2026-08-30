export default function AlertCenter({ alerts, onSelectStation }) {
  return (
    <div className="alert-center">
      <h3 className="alert-center-title">Anomaly alert center</h3>
      {alerts.length === 0 && <p className="alert-empty mono">No active anomalies.</p>}
      {alerts.map(a => {
        const time = new Date(a.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        
        return (
          <button 
            key={a.station_id} 
            className="alert-item" 
            onClick={() => onSelectStation(a.station_id)}
          >
            <span className="alert-item-dot" />
            <div className="alert-item-body">
              <span className="alert-item-title">
                {a.name} <span className="mono">· {a.anomaly.type}</span>
              </span>
              <span className="alert-item-sub">
                {time} · {a.anomaly.affected_parameter} · <span style={{ whiteSpace: 'nowrap' }}>{Math.round(a.anomaly.confidence * 100)}% confidence</span>
              </span>
            </div>
          </button>
        )
      })}
    </div>
  )
}