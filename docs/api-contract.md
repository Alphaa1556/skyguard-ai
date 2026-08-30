# API contract — SkyGuard AI

Locked on Day 0. Any change must be agreed by both frontend and backend leads before merging.

## `POST /ingest`
Station sends a reading in.
```json
{
  "station_id": "AWS-IND-MH-001",
  "timestamp": "2026-08-29T00:57:23Z",
  "location": { "latitude": 18.9894, "longitude": 73.1175 },
  "readings": { "temperature_c": 28.4, "pressure_hpa": 1008.2, "humidity_pct": 82.5 }
}
```

## `GET /stations/{id}/status`
Dashboard polls this (or subscribes via WebSocket).
```json
{
  "station_id": "AWS-IND-MH-001",
  "timestamp": "2026-08-29T00:57:23Z",
  "readings": { "temperature_c": 28.4, "pressure_hpa": 1008.2, "humidity_pct": 82.5 },
  "anomaly": {
    "is_anomaly": true,
    "type": "spike",
    "confidence": 0.87,
    "explanation": "Temperature deviates 4.2 std-dev from expected pattern; pressure/humidity remained stable, indicating sensor fault rather than genuine weather event.",
    "affected_parameter": "temperature_c"
  },
  "sensor_health": "degraded"
}
```
`anomaly.type` enum: `none | spike | flatline | drift | noise | cross_sensor`

## `GET /stations`
For the 3D map view.
```json
[
  {
    "station_id": "AWS-IND-MH-001",
    "name": "Mumbai Coastal AWS",
    "city": "Mumbai",
    "state": "Maharashtra",
    "country": "India",
    "latitude": 19.076,
    "longitude": 72.8777,
    "health": "normal",
    "feed_url": "https://city.imd.gov.in/citywx/city_weather.php?id=43003"
  }
]
```

## `POST /feedback` (stretch goal)
Human-in-the-loop correction.
```json
{ "station_id": "AWS-IND-MH-001", "timestamp": "2026-08-29T00:57:23Z", "confirmed": false, "note": "false alarm - real heatwave" }
```
