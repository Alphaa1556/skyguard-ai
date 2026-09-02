const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

const STATION_COLORS = {
  normal: '#16e0b4',
  degraded: '#ffb020',
  anomaly: '#ff4d5e',
}

export const DEFAULT_STATIONS = [
  { station_id: 'AWS-IND-MH-001', name: 'Mumbai Coastal AWS', city: 'Mumbai', state: 'Maharashtra', latitude: 19.076, longitude: 72.8777, health: 'normal', color: STATION_COLORS.normal, feedUrl: 'https://mausam.imd.gov.in/' },
  { station_id: 'AWS-IND-DL-011', name: 'Delhi Plains AWS', city: 'New Delhi', state: 'Delhi', latitude: 28.6139, longitude: 77.209, health: 'normal', color: STATION_COLORS.normal, feedUrl: 'https://city.imd.gov.in/citywx/city_weather.php?id=42182' },
  { station_id: 'AWS-IND-KA-004', name: 'Bangalore Plateau AWS', city: 'Bengaluru', state: 'Karnataka', latitude: 12.9716, longitude: 77.5946, health: 'degraded', color: STATION_COLORS.degraded, feedUrl: 'https://city.imd.gov.in/citywx/city_weather.php?id=43295' },
  { station_id: 'AWS-IND-TN-003', name: 'Chennai Coastal AWS', city: 'Chennai', state: 'Tamil Nadu', latitude: 13.0827, longitude: 80.2707, health: 'anomaly', color: STATION_COLORS.anomaly, feedUrl: 'https://city.imd.gov.in/citywx/city_weather.php?id=43279' },
  { station_id: 'AWS-IND-WB-007', name: 'Kolkata Delta AWS', city: 'Kolkata', state: 'West Bengal', latitude: 22.5726, longitude: 88.3639, health: 'normal', color: STATION_COLORS.normal, feedUrl: 'https://city.imd.gov.in/citywx/city_weather.php?id=42807' },
  { station_id: 'AWS-IND-GJ-001', name: 'Ahmedabad Semi-Arid AWS', city: 'Ahmedabad', state: 'Gujarat', latitude: 23.0225, longitude: 72.5714, health: 'normal', color: STATION_COLORS.normal, feedUrl: 'https://city.imd.gov.in/citywx/city_weather.php?id=42647' },
  { station_id: 'AWS-IND-UP-001', name: 'Lucknow Central AWS', city: 'Lucknow', state: 'Uttar Pradesh', latitude: 26.8467, longitude: 80.9462, health: 'normal', color: STATION_COLORS.normal, feedUrl: 'https://city.imd.gov.in/' },
  { station_id: 'AWS-IND-KL-001', name: 'Trivandrum Tropical AWS', city: 'Thiruvananthapuram', state: 'Kerala', latitude: 8.5241, longitude: 76.9366, health: 'normal', color: STATION_COLORS.normal, feedUrl: 'https://city.imd.gov.in/' },
]

export async function fetchStations() {
  const response = await fetch(`${API_BASE}/stations`)
  if (!response.ok) {
    return DEFAULT_STATIONS
  }
  const stations = await response.json()
  return stations.map((station) => {
    const fallback = DEFAULT_STATIONS.find((candidate) => candidate.station_id === station.station_id)
    const health = (station.health || fallback?.health || 'normal').toLowerCase()
    const color = station.color || STATION_COLORS[health] || STATION_COLORS.normal

    return {
      ...station,
      health,
      color,
      name: station.name || station.station_id,
      city: station.city || fallback?.city || station.station_id,
      state: station.state || fallback?.state || 'India',
      country: station.country || 'India',
      feedUrl: station.feed_url || fallback?.feedUrl || 'https://mausam.imd.gov.in/',
    }
  })
}

export async function fetchStationStatus(stationId) {
  const response = await fetch(`${API_BASE}/stations/${stationId}/status`)
  if (!response.ok) {
    const fallback = DEFAULT_STATIONS.find((station) => station.station_id === stationId)
    return {
      station_id: stationId,
      name: fallback?.name || stationId,
      city: fallback?.city || stationId,
      state: fallback?.state || 'India',
      timestamp: new Date().toISOString(),
      readings: { temperature_c: 27, pressure_hpa: 1008, humidity_pct: 65 },
      series: [
        { time: '00:00', temperature_c: 27, pressure_hpa: 1008, humidity_pct: 65 },
        { time: '00:05', temperature_c: 27.2, pressure_hpa: 1008.1, humidity_pct: 64.8 },
      ],
      anomaly: { is_anomaly: false, type: 'none', confidence: 0.02, explanation: 'Fallback status used because the backend is unavailable.', affected_parameter: null },
      sensor_health: fallback?.health || 'normal',
    }
  }

  const result = await response.json()
  const fallback = DEFAULT_STATIONS.find((station) => station.station_id === stationId)
  return {
    ...result,
    name: fallback?.name || result.station_id,
    city: fallback?.city || result.station_id,
    state: fallback?.state || 'India',
    country: fallback?.country || 'India',
    feedUrl: fallback?.feedUrl || 'https://mausam.imd.gov.in/',
    series: [
      { time: '00:00', temperature_c: result.readings.temperature_c - 0.5, pressure_hpa: result.readings.pressure_hpa - 0.8, humidity_pct: result.readings.humidity_pct - 2.2 },
      { time: '00:05', temperature_c: result.readings.temperature_c - 0.2, pressure_hpa: result.readings.pressure_hpa - 0.4, humidity_pct: result.readings.humidity_pct - 1.0 },
      { time: '00:10', temperature_c: result.readings.temperature_c, pressure_hpa: result.readings.pressure_hpa, humidity_pct: result.readings.humidity_pct },
    ],
  }
}
