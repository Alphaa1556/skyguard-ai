import { useEffect, useState } from 'react'
import { API_BASE } from '../data/stations'

const RECONNECT_DELAY_MS = 750

function getSocketUrl() {
  const protocol = API_BASE.startsWith('https') ? 'wss' : 'ws'
  const host = API_BASE.replace(/^https?:\/\//, '').replace(/\/$/, '')
  return `${protocol}://${host}/ws`
}

function isStationStatusMessage(value) {
  return Boolean(
    value &&
      typeof value === 'object' &&
      typeof value.station_id === 'string' &&
      value.readings &&
      typeof value.readings === 'object' &&
      value.anomaly &&
      typeof value.anomaly === 'object' &&
      typeof value.sensor_health === 'string'
  )
}

export default function useStationSocket() {
  const [latestData, setLatestData] = useState(null)
  const [connectionState, setConnectionState] = useState('connecting')

  useEffect(() => {
    let socket
    let reconnectTimer
    let stopped = false

    const connect = () => {
      if (stopped) return

      setConnectionState('connecting')
      socket = new WebSocket(getSocketUrl())

      socket.onopen = () => {
        setConnectionState('open')
      }

      socket.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data)
          if (isStationStatusMessage(message)) setLatestData(message)
        } catch {
          // Ignore malformed messages and keep the live connection open.
        }
      }

      socket.onerror = () => {
        socket.close()
      }

      socket.onclose = () => {
        if (stopped) return
        setConnectionState('reconnecting')
        reconnectTimer = window.setTimeout(connect, RECONNECT_DELAY_MS)
      }
    }

    connect()

    return () => {
      stopped = true
      window.clearTimeout(reconnectTimer)
      socket?.close()
    }
  }, [])

  return { latestData, connectionState }
}
