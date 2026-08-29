import { useEffect, useRef, useState } from 'react'
import './Hero.css'

const STATION_DOTS = [
  { x: 22, y: 30, delay: 0 },
  { x: 68, y: 18, delay: 0.6 },
  { x: 45, y: 52, delay: 1.1 },
  { x: 82, y: 60, delay: 0.3 },
  { x: 15, y: 68, delay: 1.6 },
  { x: 58, y: 78, delay: 0.9 },
  { x: 88, y: 30, delay: 1.9 },
]

// Builds an SVG path for a waveform. `spike` injects one sharp anomalous
// deviation partway through — the visual argument for the whole product.
function buildWavePath(spike) {
  const w = 900
  const h = 140
  const mid = h / 2
  const points = []
  const n = 120
  for (let i = 0; i <= n; i++) {
    const x = (i / n) * w
    let y = mid + Math.sin(i / 6) * 14 + Math.sin(i / 2.3) * 4
    if (spike && i > 62 && i < 74) {
      const t = (i - 62) / 12
      y -= Math.sin(t * Math.PI) * 70
    }
    points.push([x, y])
  }
  return 'M ' + points.map(p => p.join(',')).join(' L ')
}

export default function Hero({ onExplore }) {
  const [phase, setPhase] = useState('calm') // calm -> flagging -> calm
  const [path, setPath] = useState(buildWavePath(false))

  useEffect(() => {
    let mounted = true
    const cycle = () => {
      if (!mounted) return
      setPhase('flagging')
      setPath(buildWavePath(true))
      setTimeout(() => {
        if (!mounted) return
        setPhase('calm')
        setPath(buildWavePath(false))
      }, 2200)
    }
    const interval = setInterval(cycle, 5200)
    const first = setTimeout(cycle, 1800)
    return () => { mounted = false; clearInterval(interval); clearTimeout(first) }
  }, [])

  return (
    <section className="hero">
      <div className="hero-field" aria-hidden="true">
        <svg className="hero-sweep" viewBox="0 0 100 100" preserveAspectRatio="none">
          <circle cx="50" cy="50" r="46" className="ring ring-1" />
          <circle cx="50" cy="50" r="32" className="ring ring-2" />
          <circle cx="50" cy="50" r="18" className="ring ring-3" />
          <line x1="50" y1="50" x2="50" y2="4" className="sweep-arm" />
          {STATION_DOTS.map((d, i) => (
            <circle
              key={i}
              cx={d.x} cy={d.y} r="1.4"
              className={`station-dot ${phase === 'flagging' && i === 2 ? 'station-dot--alert' : ''}`}
              style={{ animationDelay: `${d.delay}s` }}
            />
          ))}
        </svg>
      </div>

      <div className="hero-content">
        <div className="hero-eyebrow mono">
          <span className={`status-pip ${phase === 'flagging' ? 'status-pip--alert' : ''}`} />
          {phase === 'flagging' ? 'ANOMALY FLAGGED · AWS-IND-MH-002' : 'MONITORING 6 STATIONS · ALL SYSTEMS NOMINAL'}
        </div>

        <h1 className="hero-title">
          Existing systems ask<br />
          <em>if</em> it&rsquo;s unusual.<br />
          <span className="hero-title-accent">We ask why.</span>
        </h1>

        <p className="hero-sub">
          SkyGuard AI watches India&rsquo;s Automatic Weather Stations in real time, tells sensor
          faults apart from genuine weather events, and explains every flag in plain language —
          built for MoES / IMD disaster management.
        </p>

        <div className="hero-wave-panel">
          <svg viewBox="0 0 900 140" className="hero-wave-svg" preserveAspectRatio="none">
            <path d={path} className={`hero-wave-path ${phase === 'flagging' ? 'hero-wave-path--alert' : ''}`} />
          </svg>
          <div className="hero-wave-label mono">
            temperature_c · AWS-IND-MH-002
            {phase === 'flagging' && <span className="hero-wave-tag">spike · 0.87 confidence</span>}
          </div>
        </div>

        <div className="hero-actions">
          <button className="btn-primary" onClick={onExplore}>Open dashboard</button>
          <a className="btn-ghost" href="#stations">View stations ↓</a>
        </div>
      </div>
    </section>
  )
}
