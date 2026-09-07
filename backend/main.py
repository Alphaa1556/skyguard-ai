import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

import joblib
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from features import StationFeatureBuilder

try:
    import lstm_drift_detector
except (ImportError, OSError):
    lstm_drift_detector = None

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
    {"station_id": "AWS-IND-MH-001", "name": "Mumbai Coastal AWS", "city": "Mumbai", "state": "Maharashtra", "latitude": 19.0760, "longitude": 72.8777, "feed_url": "https://city.imd.gov.in/citywx/city_weather.php?id=43003"},
    {"station_id": "AWS-IND-DL-011", "name": "Delhi Plains AWS", "city": "New Delhi", "state": "Delhi", "latitude": 28.6139, "longitude": 77.2090, "feed_url": "https://city.imd.gov.in/citywx/city_weather.php?id=42182"},
    {"station_id": "AWS-IND-KA-004", "name": "Bangalore Plateau AWS", "city": "Bengaluru", "state": "Karnataka", "latitude": 12.9716, "longitude": 77.5946, "seed_fault": "spike", "feed_url": "https://city.imd.gov.in/citywx/city_weather.php?id=43295"},
    {"station_id": "AWS-IND-TN-003", "name": "Chennai Coastal AWS", "city": "Chennai", "state": "Tamil Nadu", "latitude": 13.0827, "longitude": 80.2707, "seed_fault": "cross_sensor", "feed_url": "https://city.imd.gov.in/citywx/city_weather.php?id=43279"},
    {"station_id": "AWS-IND-WB-007", "name": "Kolkata Delta AWS", "city": "Kolkata", "state": "West Bengal", "latitude": 22.5726, "longitude": 88.3639, "feed_url": "https://city.imd.gov.in/citywx/city_weather.php?id=42807"},
    {"station_id": "AWS-IND-GJ-001", "name": "Ahmedabad Semi-Arid AWS", "city": "Ahmedabad", "state": "Gujarat", "latitude": 23.0225, "longitude": 72.5714, "feed_url": "https://city.imd.gov.in/citywx/city_weather.php?id=42647"},
    {"station_id": "AWS-IND-UP-001", "name": "Lucknow Central AWS", "city": "Lucknow", "state": "Uttar Pradesh", "latitude": 26.8467, "longitude": 80.9462, "feed_url": "https://mausam.imd.gov.in/"},
    {"station_id": "AWS-IND-KL-001", "name": "Trivandrum Tropical AWS", "city": "Thiruvananthapuram", "state": "Kerala", "latitude": 8.5241, "longitude": 76.9366, "feed_url": "https://mausam.imd.gov.in/"},
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
    """
    Populate the in-memory station store with a realistic Indian AWS inventory.

    Two stations (Bangalore, Chennai) are seeded with a REAL fault so the demo
    shows genuine detection output, not a hardcoded label. Each such station
    gets fed a normal baseline reading first (to establish rolling history for
    its StationFeatureBuilder), then a second reading shaped like an actual
    fault — this matters especially for the physics-informed cross_sensor
    rule, which needs at least one prior reading to compare against.
    """
    for station in DEMO_STATIONS:
        station_id = station["station_id"]
        if station_id in _stations:
            continue

        baseline = Readings(**DEMO_READINGS[station_id])
        seed_fault = station.get("seed_fault")

        if seed_fault is None:
            # No fault intended — a SINGLE clean detection call. Calling
            # _detect_anomaly twice with identical values (as an earlier
            # version of this function did) creates an artificial "value
            # repeated" pattern that the flatline-sensitive model picks up
            # on, incorrectly flagging every normal station.
            final_readings = baseline
            anomaly = _detect_anomaly(station_id, final_readings)
        else:
            # Establish rolling history first with a few slightly-varying
            # normal baseline readings — the physics rule requires at least 3
            # prior readings in its humidity-gated baseline before it'll trust
            # a comparison (see features.py), and using distinct values here
            # (rather than repeating the exact same one) avoids tripping the
            # flatline-sensitive model on an artificial "value didn't change"
            # pattern. THEN feed a genuinely different, fault-shaped reading.
            for i, jitter in enumerate([-0.2, 0.15, -0.1, 0.05]):
                _detect_anomaly(
                    station_id,
                    Readings(
                        temperature_c=baseline.temperature_c + jitter,
                        pressure_hpa=baseline.pressure_hpa + jitter,
                        humidity_pct=baseline.humidity_pct + jitter,
                    ),
                )

            if seed_fault == "cross_sensor":
                # Humidity pinned near saturation while temperature rises above
                # the baseline just established — triggers check_cross_sensor_rule().
                final_readings = Readings(
                    temperature_c=baseline.temperature_c + 4.0,
                    pressure_hpa=baseline.pressure_hpa,
                    humidity_pct=95.0,
                )
            else:  # "spike"
                final_readings = Readings(
                    temperature_c=baseline.temperature_c + 12.0,
                    pressure_hpa=baseline.pressure_hpa,
                    humidity_pct=baseline.humidity_pct,
                )

            anomaly = _detect_anomaly(station_id, final_readings)

        # Health label reflects the REAL detection result, not a hardcoded
        # guess — cross_sensor (our physics-rule differentiator) gets the
        # most severe "anomaly" label, any other real detection is "degraded",
        # otherwise "normal".
        if anomaly.type == AnomalyType.cross_sensor:
            health = "anomaly"
        elif anomaly.is_anomaly:
            health = "degraded"
        else:
            health = "normal"

        _stations[station_id] = StationStatus(
            station_id=station_id,
            timestamp=datetime.now(timezone.utc),
            readings=final_readings,
            anomaly=anomaly,
            sensor_health=health,
        )
        _locations[station_id] = Location(
            latitude=station["latitude"],
            longitude=station["longitude"],
        )


@app.on_event("startup")
def startup_event() -> None:
    seed_demo_data()


# ---------------------------------------------------------------------------
# Anomaly detection — loads a model trained by train_and_evaluate.py against
# Bhakti's real synthetic dataset (see backend/data/), instead of training on
# inline placeholder data. Combines the ML model with a physics-informed rule
# for cross_sensor faults (see features.py — PRD Section 4.4 hybrid approach).
#
# Falls back to training on synthetic placeholder data ONLY if model.joblib /
# feature_stats.json aren't present yet (e.g. a teammate hasn't run
# train_and_evaluate.py locally) — so the API still works out of the box.
# ---------------------------------------------------------------------------

MODEL_PATH = "model.joblib"
FEATURE_STATS_PATH = "feature_stats.json"


def _load_or_train_fallback():
    if os.path.exists(MODEL_PATH) and os.path.exists(FEATURE_STATS_PATH):
        model = joblib.load(MODEL_PATH)
        with open(FEATURE_STATS_PATH, "r") as f:
            feature_stats = json.load(f)
        print(f"Loaded trained model from {MODEL_PATH}")
        return model, feature_stats

    # Fallback: train a quick placeholder model on synthetic normal data so the
    # API still works if someone hasn't run train_and_evaluate.py yet.
    print(f"WARNING: {MODEL_PATH} not found — training a placeholder model on "
          f"synthetic data. Run train_and_evaluate.py for the real trained model.")
    from sklearn.ensemble import IsolationForest

    feature_stats = {
        "temperature_c": {"mean": 27.0, "std": 5.0},
        "pressure_hpa": {"mean": 1010.0, "std": 6.0},
        "humidity_pct": {"mean": 65.0, "std": 15.0},
    }
    rng = np.random.default_rng(42)
    n = 2000
    temp = rng.normal(feature_stats["temperature_c"]["mean"], feature_stats["temperature_c"]["std"], n)
    pressure = rng.normal(feature_stats["pressure_hpa"]["mean"], feature_stats["pressure_hpa"]["std"], n)
    humidity = np.clip(rng.normal(feature_stats["humidity_pct"]["mean"], feature_stats["humidity_pct"]["std"], n), 0, 100)

    # Build matching feature vectors (temporal features default to 0 since
    # this fallback has no real sequential history) so shape matches the real
    # trained model — 13 features: 3 raw + 3 delta + 3 rolling_std + 1 stale
    # streak + 3 long-term deviation.
    zeros = np.zeros((n, 10))
    X_train = np.column_stack([temp, pressure, humidity, zeros])

    model = IsolationForest(n_estimators=100, contamination=0.05, random_state=42)
    model.fit(X_train)
    return model, feature_stats


_model, _feature_stats = _load_or_train_fallback()

# One StationFeatureBuilder per station, kept alive across requests so it
# reflects that station's real recent history — same class used in training.
_feature_builders: dict[str, StationFeatureBuilder] = defaultdict(StationFeatureBuilder)

# ---------------------------------------------------------------------------
# LSTM-Autoencoder drift detector — a THIRD signal, specifically added
# because the engineered long_dev feature (features.py) can't reliably
# separate genuine drift from ordinary diurnal temperature swings, which are
# often the same order of magnitude. See lstm_drift_detector.py for the full
# rationale and train_and_evaluate.py's evaluation output for the measured
# recall/precision trade-off (drift recall 19.9% -> ~63%, at some FPR cost).
#
# Falls back to running WITHOUT the LSTM signal if its artifacts aren't
# present yet (e.g. a teammate hasn't re-run train_and_evaluate.py since
# this was added) — the API still works, just without drift coverage.
# ---------------------------------------------------------------------------

LSTM_WEIGHTS_PATH = "lstm_drift_model.pt"
LSTM_CONFIG_PATH = "lstm_drift_config.json"
_lstm_model = None
_lstm_scaler_stats = None
_lstm_threshold = None

if lstm_drift_detector and os.path.exists(LSTM_WEIGHTS_PATH) and os.path.exists(LSTM_CONFIG_PATH):
    _lstm_model, _lstm_scaler_stats, _lstm_threshold = lstm_drift_detector.load_artifacts(
        LSTM_WEIGHTS_PATH, LSTM_CONFIG_PATH
    )
    print(f"Loaded LSTM drift detector from {LSTM_WEIGHTS_PATH}")
else:
    print(f"WARNING: {LSTM_WEIGHTS_PATH} not found — running WITHOUT the LSTM drift "
          f"signal. Run train_and_evaluate.py to generate it (drift recall will stay "
          f"low without it — see features.py's v4 fix note).")

_drift_detectors = {}


def _get_drift_detector(station_id: str):
    if lstm_drift_detector is None or _lstm_model is None:
        return None
    if station_id not in _drift_detectors:
        _drift_detectors[station_id] = lstm_drift_detector.DriftDetector(
            _lstm_model, _lstm_scaler_stats, _lstm_threshold
        )
    return _drift_detectors[station_id]


def _detect_anomaly(station_id: str, readings: Readings) -> AnomalyResult:
    builder = _feature_builders[station_id]
    feature_vector = builder.update_and_build(
        readings.temperature_c, readings.pressure_hpa, readings.humidity_pct
    ).reshape(1, -1)

    ml_prediction = _model.predict(feature_vector)[0]  # -1 = anomaly, 1 = normal
    score = _model.decision_function(feature_vector)[0]  # higher = more "normal"
    ml_is_anomaly = ml_prediction == -1

    # Physics-informed rule (checked AFTER update_and_build, so it sees this
    # reading's history): catches cross-sensor faults the ML model tends to
    # miss once temporal features are added, per the PRD's hybrid ML +
    # physics-rule approach (Section 4.4).
    physics_flag = builder.check_cross_sensor_rule()

    # LSTM-Autoencoder drift signal — see the module-level comment above for
    # why this exists as a separate detector rather than another engineered
    # feature. Returns None until the station has WINDOW_SIZE readings of
    # history (cold start), so brand-new stations won't get a drift flag
    # from their first few readings.
    drift_detector = _get_drift_detector(station_id)
    drift_flag = drift_detector.is_drift(
        readings.temperature_c, readings.pressure_hpa, readings.humidity_pct
    ) if drift_detector is not None else False

    is_anomaly = ml_is_anomaly or physics_flag or drift_flag

    # Rough 0-1 confidence from the raw decision score — not calibrated, just
    # enough to show something meaningful for now. Physics-rule-only and
    # drift-only flags get a fixed moderate confidence since they don't have
    # an ML score.
    confidence = float(np.clip(0.5 - score, 0.0, 1.0)) if ml_is_anomaly else (
        0.7 if physics_flag else (0.65 if drift_flag else 0.0)
    )

    affected_parameter = None
    anomaly_type = AnomalyType.none
    explanation = "Reading falls within the expected range for temperature, pressure, and humidity."

    if physics_flag:
        # Physics rule takes priority for the explanation — it identifies a
        # SPECIFIC, well-understood fault signature, whereas the ML model's
        # z-score explanation below is a more generic fallback.
        anomaly_type = AnomalyType.cross_sensor
        affected_parameter = "multiple"
        explanation = (
            "Humidity is pinned near saturation while temperature is simultaneously above its "
            "recent average — this combination violates the expected inverse temperature/humidity "
            "relationship and is a strong signal of a cross-sensor fault rather than genuine weather."
        )
    elif drift_flag:
        # Drift takes priority over the generic ML/z-score explanation below
        # for the same reason as physics_flag — it identifies a specific
        # fault signature (gradual deviation from the station's learned
        # normal pattern) that the ML model's single-reading z-score can't
        # express, since drift is only visible across a sequence of readings.
        anomaly_type = AnomalyType.drift
        affected_parameter = None
        explanation = (
            "Recent readings deviate gradually from this station's learned normal pattern in a way "
            "that ordinary day-to-day weather variation doesn't — consistent with slow sensor "
            "calibration drift rather than a sudden fault or genuine weather change."
        )
    elif ml_is_anomaly:
        # Identify which parameter deviates most, using simple z-scores —
        # placeholder for Ronak's real anomaly-type classification later.
        values = {
            "temperature_c": readings.temperature_c,
            "pressure_hpa": readings.pressure_hpa,
            "humidity_pct": readings.humidity_pct,
        }
        z_scores = {
            name: abs((val - _feature_stats[name]["mean"]) / _feature_stats[name]["std"])
            for name, val in values.items()
        }
        affected_parameter = max(z_scores, key=z_scores.get)
        z = z_scores[affected_parameter]
        anomaly_type = AnomalyType.spike
        explanation = (
            f"{affected_parameter} deviates {z:.1f} standard deviations from the expected pattern, "
            f"while other readings are broadly consistent — flagged as a likely sensor anomaly rather "
            f"than a genuine weather event."
        )

    return AnomalyResult(
        is_anomaly=is_anomaly,
        type=anomaly_type,
        confidence=round(confidence, 2),
        explanation=explanation,
        affected_parameter=affected_parameter,
    )


@app.get("/")
def root():
    return {"service": "SkyGuard AI", "status": "ok"}


@app.post("/ingest", response_model=StationStatus)
def ingest(payload: IngestPayload):
    """Receive a reading, run it through the anomaly detector, store + return the result."""
    anomaly = _detect_anomaly(payload.station_id, payload.readings)

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