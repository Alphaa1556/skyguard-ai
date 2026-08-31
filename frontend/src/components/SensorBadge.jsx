const HEALTH_META = {
  normal: { label: 'Normal', color: 'var(--teal)', dim: 'var(--teal-dim)' },
  nominal: { label: 'Normal', color: 'var(--teal)', dim: 'var(--teal-dim)' },
  degraded: { label: 'Degraded', color: 'var(--amber)', dim: 'var(--amber-dim)' },
  anomaly: { label: 'Anomaly', color: 'var(--red)', dim: 'var(--red-dim)' },
}

export default function SensorBadge({ health }) {
  const meta = HEALTH_META[health] || HEALTH_META.normal
  
  return (
    <span className="badge mono" style={{ color: meta.color, background: meta.dim }}>
      <span className="badge-dot" style={{ background: meta.color }} />
      {meta.label}
    </span>
  )
}