import { useEffect, useRef, useState } from 'react'
import Hero from './components/Hero'
import Dashboard from './components/Dashboard'
import SatelliteIntro from './components/SatelliteIntro'
import './App.css'

export default function App() {
  const dashboardRef = useRef(null)
  const [introActive, setIntroActive] = useState(true)

  // Skip the boot sequence entirely for users who've asked for reduced motion.
  useEffect(() => {
    const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (prefersReduced) setIntroActive(false)
  }, [])

  // Lock page scroll while the intro overlay is up.
  useEffect(() => {
    document.body.style.overflow = introActive ? 'hidden' : ''
    return () => { document.body.style.overflow = '' }
  }, [introActive])

  const scrollToDashboard = () => {
    dashboardRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  return (
    <div className="app">
      {introActive && <SatelliteIntro onDone={() => setIntroActive(false)} />}
      <header className="site-header">
        <div className="site-brand mono">SKYGUARD_AI</div>
        <nav className="site-nav mono">
          <a href="#stations">Stations</a>
          <span className="site-nav-tag">PS 26073 · IMD</span>
        </nav>
      </header>
      <Hero onExplore={scrollToDashboard} />
      <div ref={dashboardRef}>
        <Dashboard />
      </div>
      <footer className="site-footer mono">
        Built for Ministry of Earth Sciences (MoES) · India Meteorological Department — disaster management
      </footer>
    </div>
  )
}
