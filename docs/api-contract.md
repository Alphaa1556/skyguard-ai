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
  { "station_id": "AWS-IND-MH-001", "latitude": 18.9894, "longitude": 73.1175, "health": "normal" },
  { "station_id": "AWS-IND-KA-004", "latitude": 12.9716, "longitude": 77.5946, "health": "anomaly" }
]
```

## `POST /feedback` (stretch goal)
Human-in-the-loop correction.
```json
{ "station_id": "AWS-IND-MH-001", "timestamp": "2026-08-29T00:57:23Z", "confirmed": false, "note": "false alarm - real heatwave" }
```
