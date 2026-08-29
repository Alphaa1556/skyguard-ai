import { useRef } from 'react'
import Hero from './components/Hero'
import Dashboard from './components/Dashboard'
import './App.css'

export default function App() {
  const dashboardRef = useRef(null)

  const scrollToDashboard = () => {
    dashboardRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  return (
    <div className="app">
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
