from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sklearn.ensemble import IsolationForest

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
    name: str
    city: str
    state: str
    country: str = "India"
    latitude: float
    longitude: float
    health: str
    feed_url: str


# In-memory store for now — swap for a time-series DB once the pipeline is real.
# Note: this resets every time the server restarts.
_stations: dict[str, StationStatus] = {}
_locations: dict[str, Location] = {}

DEMO_STATIONS = [
    {"station_id": "AWS-IND-MH-001", "name": "Mumbai Coastal AWS", "city": "Mumbai", "state": "Maharashtra", "latitude": 19.0760, "longitude": 72.8777, "health": "normal", "feed_url": "https://city.imd.gov.in/citywx/city_weather.php?id=43003"},
    {"station_id": "AWS-IND-DL-011", "name": "Delhi Plains AWS", "city": "New Delhi", "state": "Delhi", "latitude": 28.6139, "longitude": 77.2090, "health": "normal", "feed_url": "https://city.imd.gov.in/citywx/city_weather.php?id=42182"},
    {"station_id": "AWS-IND-KA-004", "name": "Bangalore Plateau AWS", "city": "Bengaluru", "state": "Karnataka", "latitude": 12.9716, "longitude": 77.5946, "health": "degraded", "feed_url": "https://city.imd.gov.in/citywx/city_weather.php?id=43295"},
    {"station_id": "AWS-IND-TN-003", "name": "Chennai Coastal AWS", "city": "Chennai", "state": "Tamil Nadu", "latitude": 13.0827, "longitude": 80.2707, "health": "anomaly", "feed_url": "https://city.imd.gov.in/citywx/city_weather.php?id=43279"},
    {"station_id": "AWS-IND-WB-007", "name": "Kolkata Delta AWS", "city": "Kolkata", "state": "West Bengal", "latitude": 22.5726, "longitude": 88.3639, "health": "normal", "feed_url": "https://city.imd.gov.in/citywx/city_weather.php?id=42807"},
    {"station_id": "AWS-IND-GJ-001", "name": "Ahmedabad Semi-Arid AWS", "city": "Ahmedabad", "state": "Gujarat", "latitude": 23.0225, "longitude": 72.5714, "health": "normal", "feed_url": "https://city.imd.gov.in/citywx/city_weather.php?id=42647"},
    {"station_id": "AWS-IND-UP-001", "name": "Lucknow Central AWS", "city": "Lucknow", "state": "Uttar Pradesh", "latitude": 26.8467, "longitude": 80.9462, "health": "normal", "feed_url": "https://mausam.imd.gov.in/"},
    {"station_id": "AWS-IND-KL-001", "name": "Trivandrum Tropical AWS", "city": "Thiruvananthapuram", "state": "Kerala", "latitude": 8.5241, "longitude": 76.9366, "health": "normal", "feed_url": "https://mausam.imd.gov.in/"},
]

DEMO_READINGS = {
    "AWS-IND-MH-001": {"temperature_c": 28.9, "pressure_hpa": 1009.2, "humidity_pct": 78.4},
    "AWS-IND-DL-011": {"temperature_c": 32.4, "pressure_hpa": 1005.5, "humidity_pct": 46.2},
    "AWS-IND-KA-004": {"temperature_c": 24.8, "pressure_hpa": 919.8, "humidity_pct": 68.1},
    "AWS-IND-TN-003": {"temperature_c": 30.2, "pressure_hpa": 1011.0, "humidity_pct": 81.9},
    "AWS-IND-WB-007": {"temperature_c": 29.4, "pressure_hpa": 1008.3, "humidity_pct": 81.3},
    "AWS-IND-GJ-001": {"temperature_c": 31.5, "pressure_hpa": 1007.0, "humidity_pct": 49.6},
    "AWS-IND-UP-001": {"temperature_c": 27.2, "pressure_hpa": 1006.1, "humidity_pct": 59.4},
    "AWS-IND-KL-001": {"temperature_c": 27.1, "pressure_hpa": 1011.4, "humidity_pct": 83.5},
}


def seed_demo_data() -> None:
    """Populate the in-memory station store with a realistic Indian AWS inventory."""
    for station in DEMO_STATIONS:
        station_id = station["station_id"]
        if station_id in _stations:
            continue

        readings = Readings(**DEMO_READINGS[station_id])
        anomaly = _detect_anomaly(readings)
        _stations[station_id] = StationStatus(
            station_id=station_id,
            timestamp=datetime.now(timezone.utc),
            readings=readings,
            anomaly=anomaly,
            sensor_health=station["health"],
        )
        _locations[station_id] = Location(
            latitude=station["latitude"],
            longitude=station["longitude"],
        )


@app.on_event("startup")
def startup_event() -> None:
    seed_demo_data()


# ---------------------------------------------------------------------------
# Baseline anomaly detection (Day 2-3 milestone)
#
# This is a fast first-pass filter, NOT the final model. Isolation Forest is
# trained on synthetic "normal" weather data at startup, since no real IMD
# dataset has been provided yet (flagged as the #1 risk in the PRD).
#
# TODO (later days):
#   - Replace/augment with LSTM-Autoencoder for real temporal pattern learning
#   - Real anomaly type classification (spike/flatline/drift/noise/cross_sensor)
#     instead of the simple heuristic below (Ronak, Day 4-5)
#   - SHAP-based explanation instead of the z-score text below (Day 5-6)
#   - Train on real/injected synthetic data once Bhakti's generator is ready,
#     instead of this quick startup baseline
# ---------------------------------------------------------------------------

FEATURE_NAMES = ["temperature_c", "pressure_hpa", "humidity_pct"]

# Rough "normal" ranges for Indian AWS stations — placeholder until real/injected
# synthetic data is wired in. Mean/std used both for training and for the
# z-score explanation below.
_FEATURE_STATS = {
    "temperature_c": {"mean": 27.0, "std": 5.0},
    "pressure_hpa": {"mean": 1010.0, "std": 6.0},
    "humidity_pct": {"mean": 65.0, "std": 15.0},
}


def _generate_synthetic_normal_data(n_samples: int = 2000, seed: int = 42) -> np.ndarray:
    rng = np.random.default_rng(seed)
    temp = rng.normal(_FEATURE_STATS["temperature_c"]["mean"], _FEATURE_STATS["temperature_c"]["std"], n_samples)
    pressure = rng.normal(_FEATURE_STATS["pressure_hpa"]["mean"], _FEATURE_STATS["pressure_hpa"]["std"], n_samples)
    humidity = rng.normal(_FEATURE_STATS["humidity_pct"]["mean"], _FEATURE_STATS["humidity_pct"]["std"], n_samples)
    humidity = np.clip(humidity, 0, 100)
    return np.column_stack([temp, pressure, humidity])


_training_data = _generate_synthetic_normal_data()
_model = IsolationForest(n_estimators=100, contamination=0.05, random_state=42)
_model.fit(_training_data)


def _detect_anomaly(readings: Readings) -> AnomalyResult:
    feature_vector = np.array([[readings.temperature_c, readings.pressure_hpa, readings.humidity_pct]])

    prediction = _model.predict(feature_vector)[0]  # -1 = anomaly, 1 = normal
    score = _model.decision_function(feature_vector)[0]  # higher = more "normal"
    is_anomaly = prediction == -1

    # Rough 0-1 confidence from the raw decision score — not calibrated, just
    # enough to show something meaningful for now.
    confidence = float(np.clip(0.5 - score, 0.0, 1.0))

    affected_parameter = None
    explanation = "Reading falls within the expected range for temperature, pressure, and humidity."

    if is_anomaly:
        # Identify which parameter deviates most, using simple z-scores —
        # placeholder for Ronak's real anomaly-type classification later.
        values = {
            "temperature_c": readings.temperature_c,
            "pressure_hpa": readings.pressure_hpa,
            "humidity_pct": readings.humidity_pct,
        }
        z_scores = {
            name: abs((val - _FEATURE_STATS[name]["mean"]) / _FEATURE_STATS[name]["std"])
            for name, val in values.items()
        }
        affected_parameter = max(z_scores, key=z_scores.get)
        z = z_scores[affected_parameter]
        explanation = (
            f"{affected_parameter} deviates {z:.1f} standard deviations from the expected pattern, "
            f"while other readings are broadly consistent — flagged as a likely sensor anomaly rather "
            f"than a genuine weather event."
        )

    return AnomalyResult(
        is_anomaly=is_anomaly,
        type=AnomalyType.spike if is_anomaly else AnomalyType.none,
        confidence=round(confidence, 2),
        explanation=explanation,
        affected_parameter=affected_parameter,
    )


@app.get("/")
def root():
    return {"service": "SkyGuard AI", "status": "ok"}


@app.post("/ingest", response_model=StationStatus)
def ingest(payload: IngestPayload):
    """Receive a reading, run it through the baseline anomaly detector, store + return the result."""
    anomaly = _detect_anomaly(payload.readings)

    result = StationStatus(
        station_id=payload.station_id,
        timestamp=payload.timestamp,
        readings=payload.readings,
        anomaly=anomaly,
        sensor_health="degraded" if anomaly.is_anomaly else "normal",
    )
    _stations[payload.station_id] = result
    _locations[payload.station_id] = payload.location
    return result


@app.get("/stations", response_model=List[StationSummary])
def list_stations():
    return [
        StationSummary(
            station_id=station_id,
            name=next((item["name"] for item in DEMO_STATIONS if item["station_id"] == station_id), station_id),
            city=next((item["city"] for item in DEMO_STATIONS if item["station_id"] == station_id), station_id),
            state=next((item["state"] for item in DEMO_STATIONS if item["station_id"] == station_id), "India"),
            latitude=_locations[station_id].latitude,
            longitude=_locations[station_id].longitude,
            health=status.sensor_health,
            feed_url=next((item["feed_url"] for item in DEMO_STATIONS if item["station_id"] == station_id), "https://mausam.imd.gov.in/"),
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