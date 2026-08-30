export default function AlertCenter({ alerts, onSelectStation }) {
  return (
    <div className="alert-center">
      <h3 className="alert-center-title">Anomaly alert center</h3>
      {alerts.length === 0 && <p className="alert-empty mono">No active anomalies.</p>}
      {alerts.map(a => (
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
              {a.anomaly.affected_parameter} · {Math.round(a.anomaly.confidence * 100)}% confidence
            </span>
          </div>
        </button>
      ))}
    </div>
  )
}