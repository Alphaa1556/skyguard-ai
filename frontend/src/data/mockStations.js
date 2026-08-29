// Mock data shaped exactly to the locked API contract.
// Swap fetchStations()/fetchStationStatus() for real calls in Day 7-8.

export const STATIONS = [
  { station_id: 'AWS-IND-MH-001', name: 'Pune', latitude: 18.5204, longitude: 73.8567, health: 'normal' },
  { station_id: 'AWS-IND-MH-002', name: 'Mumbai Colaba', latitude: 18.9067, longitude: 72.8147, health: 'anomaly' },
  { station_id: 'AWS-IND-KA-004', name: 'Bengaluru', latitude: 12.9716, longitude: 77.5946, health: 'degraded' },
  { station_id: 'AWS-IND-DL-011', name: 'New Delhi', latitude: 28.6139, longitude: 77.2090, health: 'normal' },
  { station_id: 'AWS-IND-WB-007', name: 'Kolkata', latitude: 22.5726, longitude: 88.3639, health: 'normal' },
  { station_id: 'AWS-IND-TN-003', name: 'Chennai', latitude: 13.0827, longitude: 80.2707, health: 'anomaly' },
]

// Generates a clean-looking time series with one injected fault type,
// mirroring what Bhakti's synthetic data generator will produce.
function genSeries(baseTemp, basePressure, baseHumidity, faultType) {
  const points = []
  const now = Date.now()
  for (let i = 29; i >= 0; i--) {
    const t = new Date(now - i * 60000)
    let temp = baseTemp + Math.sin(i / 4) * 1.2 + (Math.random() - 0.5) * 0.4
    let pressure = basePressure + Math.cos(i / 6) * 1.5 + (Math.random() - 0.5) * 0.3
    let humidity = baseHumidity + Math.sin(i / 5) * 3 + (Math.random() - 0.5) * 1.5

    if (faultType === 'spike' && i < 4) temp += 8.5
    if (faultType === 'flatline' && i < 8) { temp = baseTemp; pressure = basePressure; humidity = baseHumidity }
    if (faultType === 'drift' && i < 15) temp += (15 - i) * 0.35
    if (faultType === 'noise' && i < 10) temp += (Math.random() - 0.5) * 6

    points.push({
      time: t.toISOString().slice(11, 16),
      temperature_c: +temp.toFixed(1),
      pressure_hpa: +pressure.toFixed(1),
      humidity_pct: +Math.min(100, Math.max(0, humidity)).toFixed(1),
    })
  }
  return points
}

const FAULTS = {
  'AWS-IND-MH-002': { type: 'spike', confidence: 0.87, param: 'temperature_c',
    explanation: 'Temperature deviates 4.2 std-dev from expected pattern; pressure and humidity remained stable, indicating a sensor fault rather than a genuine weather event.' },
  'AWS-IND-KA-004': { type: 'drift', confidence: 0.64, param: 'temperature_c',
    explanation: 'Gradual upward drift in temperature over the last 15 readings with no corresponding pressure change — consistent with sensor calibration drift.' },
  'AWS-IND-TN-003': { type: 'flatline', confidence: 0.93, param: 'humidity_pct',
    explanation: 'Humidity sensor has returned an identical value for 8 consecutive readings — likely a stuck sensor rather than genuinely static conditions.' },
}

export function fetchStations() {
  return Promise.resolve(STATIONS)
}

export function fetchStationStatus(stationId) {
  const station = STATIONS.find(s => s.station_id === stationId)
  const fault = FAULTS[stationId]
  const series = genSeries(27 + Math.random() * 4, 1008 + Math.random() * 4, 65 + Math.random() * 15, fault?.type)
  const latest = series[series.length - 1]

  return Promise.resolve({
    station_id: stationId,
    name: station?.name,
    timestamp: new Date().toISOString(),
    readings: latest,
    series,
    anomaly: fault
      ? { is_anomaly: true, type: fault.type, confidence: fault.confidence, explanation: fault.explanation, affected_parameter: fault.param }
      : { is_anomaly: false, type: 'none', confidence: 0.02, explanation: 'All parameters within expected range.', affected_parameter: null },
    sensor_health: station?.health === 'normal' ? 'nominal' : station?.health,
  })
}
