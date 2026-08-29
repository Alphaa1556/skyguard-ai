from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="SkyGuard AI", description="Anomaly detection API for Automatic Weather Stations")

# Allow the frontend dev server to call this API during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnomalyType(str, Enum):
    none = "none"
    spike = "spike"
    flatline = "flatline"
    drift = "drift"
    noise = "noise"
    cross_sensor = "cross_sensor"


class Location(BaseModel):
    latitude: float
    longitude: float


class Readings(BaseModel):
    temperature_c: float
    pressure_hpa: float
    humidity_pct: float


class IngestPayload(BaseModel):
    station_id: str
    timestamp: datetime
    location: Location
    readings: Readings


class AnomalyResult(BaseModel):
    is_anomaly: bool
    type: AnomalyType
    confidence: float
    explanation: str
    affected_parameter: Optional[str] = None


class StationStatus(BaseModel):
    station_id: str
    timestamp: datetime
    readings: Readings
    anomaly: AnomalyResult
    sensor_health: str


class StationSummary(BaseModel):
    station_id: str
    latitude: float
    longitude: float
    health: str


# In-memory store for now — swap for a time-series DB once the pipeline is real.
# Note: this resets every time the server restarts.
_stations: dict[str, StationStatus] = {}
_locations: dict[str, Location] = {}


@app.get("/")
def root():
    return {"service": "SkyGuard AI", "status": "ok"}


@app.post("/ingest", response_model=StationStatus)
def ingest(payload: IngestPayload):
    """Receive a reading, run it through anomaly detection, store + return the result.

    TODO: replace this stub with the real detection pipeline
    (baseline Isolation Forest -> LSTM-Autoencoder + anomaly type classification + SHAP).
    """
    result = StationStatus(
        station_id=payload.station_id,
        timestamp=payload.timestamp,
        readings=payload.readings,
        anomaly=AnomalyResult(
            is_anomaly=False,
            type=AnomalyType.none,
            confidence=0.0,
            explanation="Detection pipeline not wired up yet — this is a placeholder response.",
        ),
        sensor_health="normal",
    )
    _stations[payload.station_id] = result
    _locations[payload.station_id] = payload.location
    return result


@app.get("/stations", response_model=List[StationSummary])
def list_stations():
    return [
        StationSummary(
            station_id=station_id,
            latitude=_locations[station_id].latitude,
            longitude=_locations[station_id].longitude,
            health=status.sensor_health,
        )
        for station_id, status in _stations.items()
    ]


@app.get("/stations/{station_id}/status", response_model=StationStatus)
def station_status(station_id: str):
    if station_id not in _stations:
        raise HTTPException(
            status_code=404,
            detail=f"Station '{station_id}' not found. Ingest a reading for it first via POST /ingest.",
        )
    return _stations[station_id]