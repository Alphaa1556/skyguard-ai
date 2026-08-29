import { useEffect, useRef, useState } from 'react'
import './SatelliteIntro.css'

const LOG_LINES = [
  'Initializing SkyGuard AI uplink…',
  'Connecting to AWS-IND-MH-001 … AWS-IND-TN-003',
  'Calibrating temperature / pressure / humidity channels',
  'Loading multivariate anomaly model',
  'Signal acquired — 6 stations online',
]

const LINE_GAP_MS = 620
const FIRST_LINE_DELAY_MS = 500
const SETTLE_MS = 1300
const TOTAL_MS = FIRST_LINE_DELAY_MS + LOG_LINES.length * LINE_GAP_MS + 700

export default function SatelliteIntro({ onDone }) {
  const [visibleLines, setVisibleLines] = useState(0)
  const [settled, setSettled] = useState(false)
  const [exiting, setExiting] = useState(false)
  const timers = useRef([])
  const finished = useRef(false)

  const finish = () => {
    if (finished.current) return
    finished.current = true
    setExiting(true)
    timers.current.push(setTimeout(onDone, 550))
  }

  useEffect(() => {
    LOG_LINES.forEach((_, i) => {
      timers.current.push(
        setTimeout(() => setVisibleLines(v => Math.max(v, i + 1)), FIRST_LINE_DELAY_MS + i * LINE_GAP_MS)
      )
    })
    timers.current.push(setTimeout(() => setSettled(true), SETTLE_MS))
    timers.current.push(setTimeout(finish, TOTAL_MS))
    return () => timers.current.forEach(clearTimeout)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className={`intro ${exiting ? 'intro--exiting' : ''}`} role="status" aria-live="polite">
      <div className="intro-stars" aria-hidden="true" />

      <div className={`intro-satellite-wrap ${settled ? 'intro-satellite-wrap--settled' : ''}`}>
        <span className="intro-signal-ring" aria-hidden="true" />
        <div className="intro-satellite-bob">
          <svg className="intro-satellite" viewBox="0 0 120 80" aria-hidden="true">
            <g className="panel panel-left">
              <rect x="2" y="30" width="34" height="20" rx="1.5" />
              <line x1="8" y1="30" x2="8" y2="50" />
              <line x1="16" y1="30" x2="16" y2="50" />
              <line x1="24" y1="30" x2="24" y2="50" />
              <line x1="32" y1="30" x2="32" y2="50" />
            </g>
            <rect x="42" y="26" width="36" height="28" rx="4" className="sat-body" />
            <circle cx="60" cy="40" r="3.2" className="sat-light" />
            <line x1="60" y1="26" x2="72" y2="10" className="sat-antenna" />
            <circle cx="72" cy="10" r="3" className="sat-dish" />
            <g className="panel panel-right">
              <rect x="84" y="30" width="34" height="20" rx="1.5" />
              <line x1="90" y1="30" x2="90" y2="50" />
              <line x1="98" y1="30" x2="98" y2="50" />
              <line x1="106" y1="30" x2="106" y2="50" />
              <line x1="114" y1="30" x2="114" y2="50" />
            </g>
          </svg>
        </div>
      </div>

      <div className="intro-panel">
        <div className="intro-log mono">
          {LOG_LINES.slice(0, visibleLines).map((line, i) => (
            <div key={i} className="intro-log-line">
              <span className="intro-log-caret">›</span> {line}
            </div>
          ))}
        </div>
        <div className="intro-progress-track">
          <div className="intro-progress-fill" style={{ animationDuration: `${TOTAL_MS}ms` }} />
        </div>
        <button className="intro-skip mono" onClick={finish}>Skip intro →</button>
      </div>
    </div>
  )
}
