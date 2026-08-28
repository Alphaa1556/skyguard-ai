from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from fastapi import FastAPI
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
_stations: dict[str, StationStatus] = {}


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
    return result


@app.get("/stations", response_model=List[StationSummary])
def list_stations():
    return [
        StationSummary(
            station_id=s.station_id,
            latitude=0.0,  # TODO: persist location alongside status
            longitude=0.0,
            health=s.sensor_health,
        )
        for s in _stations.values()
    ]


@app.get("/stations/{station_id}/status", response_model=StationStatus)
def station_status(station_id: str):
    if station_id not in _stations:
        return {"error": "station not found"}
    return _stations[station_id]
