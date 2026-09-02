"""
features.py

Shared temporal feature engineering for the anomaly detector — used by BOTH
train_and_evaluate.py (training/evaluation) and main.py (live inference), so
the model always sees features computed the exact same way it was trained on.
This avoids "train/serve skew" — a common bug where a model trained on one
feature definition quietly behaves differently in production because live
features are computed slightly differently.

v2 update: added a longer rolling window (LONG_WINDOW) so drift — which
unfolds over 3-10 hours — has a chance of being visible, since the original
short window (WINDOW, ~30 min) could only see sudden changes. Also added a
physics-informed rule for cross_sensor faults (see StationFeatureBuilder.
check_cross_sensor_rule), since that fault type's signature — temperature
rising while humidity is simultaneously pinned near saturation — is a known
physical implausibility (violates the usual inverse temp/humidity
correlation) that's more reliably caught by a direct domain rule than by
diluting it among many ML features. This mirrors the PRD's own suggested
hybrid ML + physics-rule approach (Section 4.4).
"""

from collections import deque
from typing import Dict

import numpy as np

RAW_FEATURE_NAMES = ["temperature_c", "pressure_hpa", "humidity_pct"]

FEATURE_NAMES = [
    "temperature_c", "pressure_hpa", "humidity_pct",
    "delta_temperature_c", "delta_pressure_hpa", "delta_humidity_pct",
    "rolling_std_temperature_c", "rolling_std_pressure_hpa", "rolling_std_humidity_pct",
    "max_stale_streak",
    "long_dev_temperature_c", "long_dev_pressure_hpa", "long_dev_humidity_pct",
]

WINDOW = 6  # ~30 min of history at 5-min intervals — catches sudden faults
LONG_WINDOW = 60  # ~5 hours — long enough to see gradual drift (which unfolds over 3-10 hrs)
STALE_EPSILON = 1e-6  # treat values closer than this as "unchanged" (float precision safety)

# Physics rule thresholds for cross_sensor detection — tuned against the
# generator's own fault definition (humidity forced to ~95% while temp rises
# 4-8C), kept a bit looser so it generalizes beyond the exact synthetic values.
CROSS_SENSOR_HUMIDITY_THRESHOLD = 88.0
CROSS_SENSOR_TEMP_DEVIATION_THRESHOLD = 1.0


class StationFeatureBuilder:
    """
    Maintains rolling per-station history and computes a temporal feature
    vector for each new reading.

    One instance should be kept alive per station — in training, one is
    created per station and fed its readings in chronological order; in
    live inference, main.py keeps one instance per station_id across
    requests so it always reflects that station's real recent history.
    """

    def __init__(self, window: int = WINDOW, long_window: int = LONG_WINDOW):
        self.window = window
        self.long_window = long_window
        self._history: Dict[str, deque] = {
            name: deque(maxlen=window) for name in RAW_FEATURE_NAMES
        }
        self._long_history: Dict[str, deque] = {
            name: deque(maxlen=long_window) for name in RAW_FEATURE_NAMES
        }
        self._stale_streak: Dict[str, int] = {name: 0 for name in RAW_FEATURE_NAMES}
        self._last_value: Dict[str, float] = {name: None for name in RAW_FEATURE_NAMES}

    def update_and_build(self, temperature_c: float, pressure_hpa: float, humidity_pct: float) -> np.ndarray:
        """Feed in a new reading, update internal state, and return its feature vector."""
        values = {
            "temperature_c": temperature_c,
            "pressure_hpa": pressure_hpa,
            "humidity_pct": humidity_pct,
        }
        deltas = {}
        rolling_stds = {}
        long_devs = {}

        for name, val in values.items():
            last = self._last_value[name]
            deltas[name] = 0.0 if last is None else val - last

            if last is not None and abs(val - last) < STALE_EPSILON:
                self._stale_streak[name] += 1
            else:
                self._stale_streak[name] = 0

            self._history[name].append(val)
            rolling_stds[name] = float(np.std(self._history[name])) if len(self._history[name]) > 1 else 0.0

            # Long-term deviation: compare current value to the mean of
            # everything seen so far in the long window, BEFORE adding the
            # current value in — this is what makes gradual drift visible,
            # since a slowly diverging value will pull away from its own
            # longer-run average even when each individual step is small.
            long_hist = self._long_history[name]
            long_devs[name] = 0.0 if len(long_hist) == 0 else float(val - np.mean(long_hist))
            long_hist.append(val)

            self._last_value[name] = val

        max_stale_streak = float(max(self._stale_streak.values()))

        return np.array([
            values["temperature_c"], values["pressure_hpa"], values["humidity_pct"],
            deltas["temperature_c"], deltas["pressure_hpa"], deltas["humidity_pct"],
            rolling_stds["temperature_c"], rolling_stds["pressure_hpa"], rolling_stds["humidity_pct"],
            max_stale_streak,
            long_devs["temperature_c"], long_devs["pressure_hpa"], long_devs["humidity_pct"],
        ])

    def check_cross_sensor_rule(self) -> bool:
        """
        Physics-informed check, evaluated AFTER update_and_build has been
        called for the current reading (so self._history reflects it).

        Temperature and humidity normally move inversely — humidity drops as
        temperature rises. If humidity is pinned near saturation WHILE
        temperature is simultaneously above its own recent average, that
        combination is physically implausible and is a strong, direct signal
        of a cross-sensor fault — more reliable here than relying on the ML
        model to rediscover this relationship among many other features.
        """
        temp_hist = self._history["temperature_c"]
        humidity_hist = self._history["humidity_pct"]
        if len(temp_hist) < 2:
            return False

        current_temp = temp_hist[-1]
        current_humidity = humidity_hist[-1]
        temp_mean = float(np.mean(temp_hist))

        return (
            current_humidity > CROSS_SENSOR_HUMIDITY_THRESHOLD
            and current_temp > temp_mean + CROSS_SENSOR_TEMP_DEVIATION_THRESHOLD
        )