"""
features.py

Shared temporal feature engineering for the anomaly detector — used by BOTH
train_and_evaluate.py (training/evaluation) and main.py (live inference), so
the model always sees features computed the exact same way it was trained on.
This avoids "train/serve skew" — a common bug where a model trained on one
feature definition quietly behaves differently in production because live
features are computed slightly differently.

Why these features: the baseline model trained on raw readings alone
(temperature_c, pressure_hpa, humidity_pct) scored very poorly on flatline
(3.9% recall) and drift (28.0% recall) faults — because a frozen or slowly
drifting reading can look perfectly plausible in isolation. These faults are
only visible when you look at how a reading compares to recent history, which
raw point-in-time values can't capture.

Added features:
  - delta_<param>:        change from the previous reading (catches sudden jumps)
  - rolling_std_<param>:  variance over a short recent window (catches noise
                           bursts, and low variance during a flatline)
  - max_stale_streak:     how many consecutive readings any parameter has
                           been unchanged (directly targets flatline faults)
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
]

WINDOW = 6  # ~30 min of history at 5-min intervals — tune later if needed
STALE_EPSILON = 1e-6  # treat values closer than this as "unchanged" (float precision safety)


class StationFeatureBuilder:
    """
    Maintains rolling per-station history and computes a temporal feature
    vector for each new reading.

    One instance should be kept alive per station — in training, one is
    created per station and fed its readings in chronological order; in
    live inference, main.py keeps one instance per station_id across
    requests so it always reflects that station's real recent history.
    """

    def __init__(self, window: int = WINDOW):
        self.window = window
        self._history: Dict[str, deque] = {
            name: deque(maxlen=window) for name in RAW_FEATURE_NAMES
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

        for name, val in values.items():
            last = self._last_value[name]
            deltas[name] = 0.0 if last is None else val - last

            if last is not None and abs(val - last) < STALE_EPSILON:
                self._stale_streak[name] += 1
            else:
                self._stale_streak[name] = 0

            self._history[name].append(val)
            rolling_stds[name] = float(np.std(self._history[name])) if len(self._history[name]) > 1 else 0.0

            self._last_value[name] = val

        max_stale_streak = float(max(self._stale_streak.values()))

        return np.array([
            values["temperature_c"], values["pressure_hpa"], values["humidity_pct"],
            deltas["temperature_c"], deltas["pressure_hpa"], deltas["humidity_pct"],
            rolling_stds["temperature_c"], rolling_stds["pressure_hpa"], rolling_stds["humidity_pct"],
            max_stale_streak,
        ])