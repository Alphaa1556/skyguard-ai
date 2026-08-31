export default function ExplainPanel({ anomaly }) {
  if (!anomaly || !anomaly.is_anomaly) return null

  const confidencePct = Math.round(anomaly.confidence * 100)

  return (
    <div className="explain-panel">
      <div className="explain-panel-head">
        <span className="explain-panel-type mono">{anomaly.type?.toUpperCase()}</span>
        <div className="confidence-bar">
          <div className="confidence-bar-track">
            <div 
              className="confidence-bar-fill" 
              style={{ width: `${confidencePct}%` }} 
            />
          </div>
          <span className="confidence-value mono">{confidencePct}% confidence</span>
        </div>
      </div>
      <p className="explain-panel-text">{anomaly.explanation}</p>
    </div>
  )
}