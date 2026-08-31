import { useEffect, useMemo, useRef, useState } from 'react'
import Globe from 'react-globe.gl'
import './Hero.css'
import { DEFAULT_STATIONS, fetchStations } from '../data/stations'

const STATION_DOTS = [
  { x: 22, y: 30, delay: 0 },
  { x: 68, y: 18, delay: 0.6 },
  { x: 45, y: 52, delay: 1.1 },
  { x: 82, y: 60, delay: 0.3 },
  { x: 15, y: 68, delay: 1.6 },
  { x: 58, y: 78, delay: 0.9 },
  { x: 88, y: 30, delay: 1.9 },
]

const WORLD_LABELS = [
  { label: 'North America', lat: 39, lng: -98 },
  { label: 'Brazil', lat: -15, lng: -52 },
  { label: 'Europe', lat: 52, lng: 15 },
  { label: 'Africa', lat: 4, lng: 20 },
  { label: 'India', lat: 22, lng: 78 },
  { label: 'China', lat: 35, lng: 104 },
  { label: 'Australia', lat: -25, lng: 133 },
]

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
  const globeRef = useRef(null)
  const [phase, setPhase] = useState('calm')
  const [path, setPath] = useState(buildWavePath(false))
  const [stations, setStations] = useState(DEFAULT_STATIONS)
  const [selectedStationId, setSelectedStationId] = useState(DEFAULT_STATIONS[0].station_id)
  const [worldPolygons, setWorldPolygons] = useState([])

  useEffect(() => {
    let active = true
    fetchStations()
      .then((items) => {
        if (!active) return
        setStations(items)
        setSelectedStationId((current) => current || items[0]?.station_id || DEFAULT_STATIONS[0].station_id)
      })
      .catch(() => {
        if (active) setStations(DEFAULT_STATIONS)
      })

    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    let active = true
    fetch('https://raw.githubusercontent.com/holtzy/D3-graph-gallery/master/DATA/world.geojson')
      .then((res) => res.json())
      .then((data) => {
        if (active && data?.features) setWorldPolygons(data.features)
      })
      .catch(() => {
        if (active) setWorldPolygons([])
      })

    return () => {
      active = false
    }
  }, [])

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

  useEffect(() => {
    if (!globeRef.current) return
    const globe = globeRef.current
    globe.controls().autoRotate = true
    globe.controls().autoRotateSpeed = 0.6
    globe.controls().enablePan = false
    globe.controls().enableZoom = true
    globe.pointOfView({ lat: 20, lng: 78, altitude: 1.8 }, 0)
  }, [])

  const selectedStation = useMemo(
    () => stations.find((station) => station.station_id === selectedStationId) ?? stations[0] ?? DEFAULT_STATIONS[0],
    [selectedStationId, stations]
  )

  const stationPoints = useMemo(
    () =>
      stations.map((station) => ({
        ...station,
        lat: station.latitude,
        lng: station.longitude,
        color: station.health === 'anomaly' ? '#ff4d5e' : station.health === 'degraded' ? '#ffb020' : '#16e0b4',
      })),
    [stations]
  )

  const labelPoints = useMemo(
    () => [
      ...WORLD_LABELS,
      ...stations.map((station) => ({
        label: `${station.city} · ${station.state}`,
        lat: station.latitude,
        lng: station.longitude,
        color: '#ffb020',
      })),
    ],
    [stations]
  )

  return (
    <section className="hero">
      <div className="hero-field" aria-hidden="true">
        <div className="radar-glow" />
        <svg className="hero-sweep" viewBox="0 0 100 100" preserveAspectRatio="none">
          <circle cx="50" cy="50" r="46" className="ring ring-1" />
          <circle cx="50" cy="50" r="32" className="ring ring-2" />
          <circle cx="50" cy="50" r="18" className="ring ring-3" />
          <line x1="50" y1="50" x2="50" y2="4" className="sweep-arm" />
          {STATION_DOTS.map((dot, index) => (
            <circle
              key={index}
              cx={dot.x}
              cy={dot.y}
              r="1.4"
              className={`station-dot ${phase === 'flagging' && index === 2 ? 'station-dot--alert' : ''}`}
              style={{ animationDelay: `${dot.delay}s` }}
            />
          ))}
        </svg>
        <span className="radar-readout radar-readout--top mono">LIVE SCAN · 360°</span>
        <span className="radar-readout radar-readout--bottom mono">AWS NETWORK / INDIA</span>
      </div>

      <div className="hero-content">
        <div className="hero-eyebrow mono">
          <span className={`status-pip ${phase === 'flagging' ? 'status-pip--alert' : ''}`} />
          {phase === 'flagging' ? `ANOMALY FLAGGED · ${selectedStation.station_id}` : `MONITORING ${stations.length} AWS STATIONS · INDIA NETWORK LIVE`}
        </div>

        <h1 className="hero-title">
          Existing systems ask<br />
          <em>if</em> it&rsquo;s unusual.<br />
          <span className="hero-title-accent">We ask why.</span>
        </h1>

        <p className="hero-sub">
          SkyGuard AI watches India&rsquo;s Automatic Weather Stations in real time, tells sensor faults apart from genuine weather events, and explains every flag in plain language — built for MoES / IMD disaster management.
        </p>

        <div className="hero-wave-panel">
          <svg viewBox="0 0 900 140" className="hero-wave-svg" preserveAspectRatio="none">
            <path d={path} className={`hero-wave-path ${phase === 'flagging' ? 'hero-wave-path--alert' : ''}`} />
          </svg>
          <div className="hero-wave-label mono">
            {selectedStation.station_id}
            {phase === 'flagging' && <span className="hero-wave-tag">spike · 0.87 confidence</span>}
          </div>
        </div>

        <div className="hero-actions">
          <button className="btn-primary" onClick={onExplore}>Open dashboard</button>
          <a className="btn-ghost" href="#stations">View stations ↓</a>
        </div>
      </div>

      <div className="hero-globe-section">
        <div className="hero-globe-heading">
          <div>
            <span className="hero-live-label mono">India AWS network</span>
            <h2>Every station, one click away</h2>
          </div>
          <span className="mono">Click a marker to select a live feed</span>
        </div>
        <div className="hero-globe-panel">
          <Globe
            ref={globeRef}
            width={900}
            height={540}
            backgroundColor="rgba(0,0,0,0)"
            showAtmosphere
            atmosphereColor="#6FE8FF"
            atmosphereAltitude={0.18}
            polygonsData={worldPolygons}
            polygonCapColor={() => 'rgba(38, 136, 167, 0.65)'}
            polygonSideColor={() => 'rgba(255,255,255,0.04)'}
            polygonStrokeColor={() => 'rgba(140, 216, 255, 0.46)'}
            polygonAltitude={(d) => (d.properties?.name === 'India' ? 0.08 : 0.02)}
            labelsData={labelPoints}
            labelLat={(d) => d.lat}
            labelLng={(d) => d.lng}
            labelText={(d) => d.label}
            labelSize={(d) => (d.label.includes('·') ? 0.9 : 0.7)}
            labelColor={(d) => (d.label.includes('·') ? '#ffb020' : '#dfe8ff')}
            labelDotRadius={0.18}
            pointsData={stationPoints}
            pointLat={(d) => d.lat}
            pointLng={(d) => d.lng}
            pointColor={(d) => d.color}
            pointAltitude={(d) => (d.station_id === selectedStationId ? 0.18 : 0.12)}
            pointRadius={(d) => (d.station_id === selectedStationId ? 0.28 : 0.18)}
            onPointClick={(point) => setSelectedStationId(point.station_id)}
          />
        </div>
        <aside className="globe-station-rail">
          <div className="globe-station-panel">
            <span className="hero-live-label mono">Selected AWS</span>
            <strong>{selectedStation.name}</strong>
            <span className="mono">{selectedStation.station_id}</span>
            <span className="mono">{selectedStation.city}, {selectedStation.state}, {selectedStation.country || 'India'}</span>
            <a href={selectedStation.feedUrl || selectedStation.feed_url} target="_blank" rel="noreferrer" className="globe-feed-link">Open original live feed →</a>
          </div>
          <div className="globe-station-list">
            {stations.map((station) => (
              <button key={station.station_id} type="button" className={`globe-station-item ${selectedStationId === station.station_id ? 'globe-station-item--active' : ''}`} onClick={() => setSelectedStationId(station.station_id)}>
                <strong>{station.city}</strong>
                <span className="mono">{station.station_id}</span>
              </button>
            ))}
          </div>
          <div className="globe-station-footer mono">{stations.length} India AWS points highlighted</div>
        </aside>
      </div>
    </section>
  )
}
